from fastapi import Request, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import json
import uuid
from typing import Optional, List
import redis.asyncio as redis
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type
from app.core.exceptions.base import AppBaseException
from app.models.user import User
from app.schemas.email import SendEmailRequest
from app.services.audit_service import AuditService, AUDIT_QUEUE_KEY, AUDIT_DLQ_KEY, MAX_QUEUE_LENGTH, MAX_DLQ_LENGTH
from app.utils.network import get_real_ip
from app.core.logging import logger
from app.core.security import safe_hash
from app.core.redis import get_redis
from app.core.config import settings


MAX_USER_AGENT_LENGTH = 180
MAX_IP_LENGTH = 45
MAX_METADATA_TO = 5
ADMIN_RATE_LIMIT_PREFIX = "admin_email"
MAX_ATTEMPTS_PER_IP = getattr(settings, "MAX_ATTEMPTS_PER_IP", 100)


class AdminEmailResponse(BaseModel):
    message: str
    status: str
    task_id: str
    expires_in: int


# ---------- Redis Helpers ----------
@retry(retry=retry_if_exception_type(redis.RedisError), wait=wait_fixed(0.5), stop=stop_after_attempt(3))
async def push_to_redis(redis_conn: redis.Redis, key: str, data: str, max_len: int, expire_seconds: int):
    async with redis_conn.pipeline(transaction=True) as pipe:
        pipe.rpush(key, data)
        pipe.ltrim(key, -max_len, -1)
        pipe.expire(key, expire_seconds)
        await pipe.execute()


@retry(retry=retry_if_exception_type(redis.RedisError), wait=wait_fixed(0.5), stop=stop_after_attempt(2))
async def push_to_dlq(redis_conn: redis.Redis, key: str, data: str):
    async with redis_conn.pipeline(transaction=True) as pipe:
        pipe.rpush(key, data)
        pipe.ltrim(key, -MAX_DLQ_LENGTH, -1)
        pipe.expire(key, 86400 * 30)
        await pipe.execute()
    logger.warning("AUDIT_DLQ_SUCCESS", extra={"key": key})  # بعد از execute


# ---------- Background Audit ----------
async def background_audit_log(admin: User, log_entry: dict, db: Optional[Session] = None, enable_db_fallback: bool = False):
    redis_conn = None
    try:
        redis_conn = await get_redis()
        raw = json.dumps(log_entry, ensure_ascii=False, default=str)
        await push_to_redis(redis_conn, AUDIT_QUEUE_KEY, raw, MAX_QUEUE_LENGTH, 86400 * 30)
        logger.debug("AUDIT_REDIS_SUCCESS", extra={"admin_id": admin.id})
        return
    except Exception as e:
        logger.exception("AUDIT_QUEUE_FAIL", extra={"admin_id": admin.id, "error": str(e)})

    if db and enable_db_fallback:
        try:
            AuditService.log(
                db=db,
                action=log_entry["action"],
                success=True,
                user_id=admin.id,
                ip=log_entry.get("ip"),
                user_agent=log_entry.get("user_agent"),
                metadata=log_entry.get("metadata"),
                flush=False,
            )
            if db.is_active:
                db.commit()
            logger.warning("AUDIT_DB_FALLBACK_OK", extra={"admin_id": admin.id})
            return
        except Exception:
            if db.is_active:
                db.rollback()
            logger.exception("AUDIT_DB_FALLBACK_FAIL", extra={"admin_id": admin.id})

    if redis_conn:
        try:
            raw = json.dumps(log_entry, ensure_ascii=False, default=str)
            await push_to_dlq(redis_conn, AUDIT_DLQ_KEY, raw)
        except Exception:
            logger.critical("AUDIT_TOTAL_LOSS", extra={"admin_id": admin.id})


# ---------- Main Service ----------
async def send_email_as_admin(
    self,
    db: Optional[Session],
    admin: User,
    request: Request,
    payload: SendEmailRequest,
    background_tasks: BackgroundTasks,
    enable_db_fallback: bool = False,
) -> AdminEmailResponse:

    # --- Admin check ---
    if not getattr(admin, "is_effective_admin", False):
        raise AppBaseException(403, {"error_code": "ADMIN_REQUIRED"})

    # --- Redis connection and Rate-limit ---
    async with await get_redis() as redis_conn:

        # Admin rate limit (daily)
        admin_key = f"{ADMIN_RATE_LIMIT_PREFIX}:limit:{admin.id}"
        count = await redis_conn.incr(admin_key)
        if count == 1:
            await redis_conn.expire(admin_key, 86400)
        if count > 500:
            raise AppBaseException(429, {"error_code": "ADMIN_RATE_LIMIT_EXCEEDED"})

        # IP rate limit (even unknown)
        client_ip = (get_real_ip(request) or "unknown")[:MAX_IP_LENGTH]
        ip_key = f"{ADMIN_RATE_LIMIT_PREFIX}:ip:{client_ip}"
        ip_count = await redis_conn.incr(ip_key)
        if ip_count == 1:
            await redis_conn.expire(ip_key, 86400)
        if ip_count > MAX_ATTEMPTS_PER_IP:
            raise AppBaseException(429, {"error_code": "IP_RATE_LIMIT_EXCEEDED"})

    # --- User agent ---
    user_agent = (request.headers.get("user-agent", "unknown") or "")[:MAX_USER_AGENT_LENGTH]

    # --- Optional request_id (truncate 200) ---
    request_id: Optional[str] = getattr(request.state, "request_id", None)
    if request_id:
        request_id = request_id[:200]

    # --- Fingerprint ---
    fingerprint = safe_hash(client_ip + user_agent)[:12]

    # --- To hashes (try/except) ---
    try:
        to_hashes: List[str] = [safe_hash(str(to)) for to in (payload.to or [])[:MAX_METADATA_TO]]
    except Exception:
        to_hashes = []

    # --- Metadata ---
    metadata = {
        "subject": payload.subject,  # required
        "to_count": len(payload.to or []),
        "to_hashes": to_hashes,
        "fingerprint": fingerprint,
    }

    # --- Log entry ---
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "ADMIN_EMAIL_REQUEST_RECEIVED",
        "admin_id": str(admin.id),
        "ip": client_ip,
        "user_agent": user_agent,
        "request_id": request_id,
        "metadata": metadata,
    }

    # --- Task ID & TTL ---
    task_id = str(uuid.uuid4())
    expires_in = getattr(settings, "EMAIL_REQUEST_TTL_SECONDS", 86400)

    # --- Background tasks ---
    background_tasks.add_task(background_audit_log, admin, log_entry, db, enable_db_fallback)
    background_tasks.add_task(
        self.policy_service.process_admin_email_request,
        db,
        admin,
        request,
        payload,
        background_tasks,
    )

    return AdminEmailResponse(
        message="Email request accepted and queued",
        status="queued",
        task_id=task_id,
        expires_in=expires_in,
    )
