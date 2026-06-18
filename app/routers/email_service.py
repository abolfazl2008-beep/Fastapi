import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Header
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.dependencies.auth import require_admin
from app.middlewares.rate_limit import limiter
from app.models.user import User
from app.schemas.email import SendEmailRequest
from app.services.email_policy_service import EmailPolicyService, EmailPolicyError
from app.models.audit_log import AuditLog
from app.service.redis_service import RedisService
from app.core.logging import logger
from app.core.ip import get_real_ip
from app.database.session import SessionLocal

router = APIRouter(prefix="/email", tags=["Email"])
email_policy_service = EmailPolicyService()
redis_service = RedisService()

MAX_BODY_SIZE = 1_000_000
IDEMPOTENCY_TTL = 24 * 3600  # 24 hours

# ------------------ Helper: per-admin daily rate limit ------------------
async def enforce_admin_daily_limit(redis: RedisService, admin_id: int):
    key = f"rl:admin_email:{admin_id}:{datetime.utcnow().date()}"
    count = await redis.increment(key, expire=86400)
    if count > 20:
        raise HTTPException(429, "Daily email limit exceeded", headers={"Retry-After": "86400"})

# ------------------ Helper: Sync DB audit in background ------------------
def log_audit_to_db_sync(audit_entry: dict):
    db_local = SessionLocal()
    try:
        db_local.add(AuditLog(**audit_entry))
        db_local.commit()
    except Exception as e:
        logger.warning("AUDIT_DB_FAILED", extra={"error": str(e)})
    finally:
        db_local.close()

# ------------------ Main Endpoint ------------------
@router.post("/send", status_code=202)
@limiter.limit("5/minute")  # global protection
async def send_email_endpoint(
    request: Request,
    payload: SendEmailRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(400, "X-Idempotency-Key header is required")

    ip = get_real_ip(request)
    task_id = str(uuid4())

    # -------------------- Atomic Idempotency --------------------
    idem_key = f"idempotency:{idempotency_key}"
    idem_data = {
        "task_id": task_id,
        "status": "processing",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "admin_id": admin.id,
    }
    was_set = await redis_service.set_key(idem_key, json.dumps(idem_data), nx=True, ex=IDEMPOTENCY_TTL)
    if not was_set:
        existing_raw = await redis_service.get_key(idem_key)
        if existing_raw:
            existing = json.loads(existing_raw)
            raise HTTPException(429, f"Duplicate request, task_id={existing.get('task_id')}")
        else:
            raise HTTPException(503, "Idempotency check failed")

    # -------------------- Rate limits & validation --------------------
    await enforce_admin_daily_limit(redis_service, admin.id)
    raw_body = await request.body()
    if len(raw_body) > MAX_BODY_SIZE:
        raise HTTPException(400, "Request body too large")

    await email_policy_service.validate_email_content(payload)

    # -------------------- Queue main background task --------------------
    background_tasks.add_task(
        email_policy_service.send_admin_email_background,
        admin_id=admin.id,
        payload=payload,
        task_id=task_id,
        idempotency_key=idempotency_key,
        ip=ip,
    )

    # -------------------- Async audit --------------------
    audit_entry = {
        "user_id": admin.id,
        "action": "ADMIN_EMAIL_QUEUED",
        "success": True,
        "metadata": {"task_id": task_id, "ip": ip},
    }
    background_tasks.add_task(redis_service.push_audit, audit_entry)
    background_tasks.add_task(log_audit_to_db_sync, audit_entry)

    return {"status": "queued", "task_id": task_id}