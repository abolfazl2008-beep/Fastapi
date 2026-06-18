import json
import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)
from redis.exceptions import RedisError
from app.core.logging import logger
from app.models.audit_log import AuditLog
from app.core.config import settings


APP_NAME = getattr(settings, "APP_NAME", "app")
AUDIT_QUEUE_KEY = f"audit:{APP_NAME}:queue"
AUDIT_DLQ_KEY = f"audit:{APP_NAME}:dlq"
MAX_QUEUE_LENGTH = getattr(settings, "AUDIT_QUEUE_MAX_LENGTH", 10000)
DLQ_EXPIRE_SECONDS = 86400 * 30


class AuditService:
    @staticmethod
    async def log(
            *,
            action: str,
            success: bool,
            redis_conn,
            db: Optional[Session] = None,
            user_id: Optional[Any] = None,
            ip: Optional[str] = None,
            user_agent: Optional[str] = None,
            metadata: Optional[Mapping[str, Any]] = None,
            request_id: Optional[str] = None,
    ) -> None:

        if redis_conn is None:
            logger.critical("AUDIT_NO_REDIS_CONN_PASSED")
            redis_available = False
        else:
            redis_available = True

        created_at_dt = datetime.now(timezone.utc).replace(microsecond=0)
        created_at_str = created_at_dt.isoformat()
        event_id = str(uuid.uuid4())


        safe_metadata = None
        if metadata:
            safe_md = {}
            for k, v in list(metadata.items())[:20]:
                try:
                    safe_md[str(k)] = str(v)[:2000]
                except Exception:
                    safe_md[str(k)] = "<conversion_error>"
            try:
                if len(json.dumps(safe_md)) < 10_000:
                    safe_metadata = safe_md
                else:
                    safe_metadata = {"truncated": True}
            except Exception:
                safe_metadata = {"serialization_error": True}

        entry = {
            "id": event_id,
            "event_id": event_id,
            "created_at": created_at_dt,
            "created_at_str": created_at_str,
            "action": action[:120],
            "success": success,
            "user_id": str(user_id)[:128] if user_id is not None else None,
            "ip": ip,
            "user_agent": (user_agent or "")[:512],
            "metadata": safe_metadata,
            "request_id": request_id[:120] if request_id else None,
        }

        entry["fingerprint"] = make_fingerprint(entry)

        summary = {
            "action": entry["action"],
            "user_id": entry["user_id"],
            "request_id": entry["request_id"],
        }

        if redis_available:
            try:
                await asyncio.wait_for(
                    AuditService._enqueue(entry, redis_conn),
                    timeout=REDIS_TIMEOUT,
                )
                return

            except asyncio.TimeoutError:
                logger.warning("AUDIT_REDIS_TIMEOUT", extra={"fingerprint": entry["fingerprint"], **summary})
            except Exception as e:
                logger.error("AUDIT_REDIS_FAIL", extra={
                    "fingerprint": entry["fingerprint"],
                    "error": str(e),
                    **summary
                })


        if db:
            try:
                db.add(AuditLog(**entry))
                db.commit()
                logger.info("AUDIT_DB_FALLBACK_OK", extra={"fingerprint": entry["fingerprint"], **summary})
                return
            except IntegrityError:
                db.rollback()
                logger.warning("AUDIT_DUPLICATE_FINGERPRINT", extra={"fingerprint": entry["fingerprint"], **summary})
                return
            except Exception:
                db.rollback()
                logger.exception("AUDIT_DB_FALLBACK_FAIL", extra={"fingerprint": entry["fingerprint"], **summary})

        # ---------- DLQ ----------
        if redis_available:
            try:
                await push_dlq_with_retry(entry, redis_conn)
                logger.warning("AUDIT_PUSHED_TO_DLQ", extra={"fingerprint": entry["fingerprint"], **summary})
            except Exception:
                logger.critical("AUDIT_TOTAL_LOSS_DLQ_FAIL", extra={"fingerprint": entry["fingerprint"], **summary})
        else:
            logger.critical("AUDIT_TOTAL_LOSS_NO_REDIS_NO_DB", extra={"fingerprint": entry["fingerprint"], **summary})
