from celery import shared_task
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from app.db.session import SessionLocal
from app.services.mfa_service import verify_mfa
from app.core.redis_service import get_redis_service, RedisService
from app.models.user import User
from app.core.logging import logger
from app.core.config import settings
from app.database.session import get_db

@shared_task(
    bind=True,
    autoretry_for=(OperationalError,),
    retry_kwargs={"max_retries": 2, "countdown": 2},
)
def mfa_verify_task(
    self,
    *,
    user_id: int,
    code: str,
    ip: str,
    ua: str,
    fingerprint: str,
    idem_key: str,
):
    redis: RedisService = get_redis_service()
    db: Session = next(get_db())

    try:
        user = db.get(User, user_id)
        if not user:
            raise MFANotConfiguredError()

        result, retry_after, lock_exceeded, fail_count = verify_mfa(
            db=db,
            user=user,
            code=code,
            ip=ip,
            user_agent=ua,
            fingerprint=fingerprint,
            redis=redis,
        )

        if lock_exceeded:
            redis.set_key(idem_key, "locked", expire=300)
            return {"status": "LOCKED", "retry_after": retry_after}

        redis.set_key(idem_key, "verified", expire=300)
        return {"status": "SUCCESS"}

    except Exception as exc:
        redis.set_key(idem_key, "failed", expire=300)
        logger.warning(
            "MFA_VERIFY_FAILED",
            extra={"user_id": user_id, "task_id": self.request.id},
        )
        raise exc
