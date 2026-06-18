from celery import shared_task
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError
from app.db.session import SessionLocal
from app.models.user import User
from app.services.audit_service import AuditService
from app.core.redis_service import RedisService
from app.core.crypto import refresh_token_hash
from app.core.redis_safe import redis_call
from app.core.user_agent import normalize_ua
from app.core.security import create_access_token, create_refresh_token
from app.core.exceptions.auth import InvalidRefreshTokenError
from app.core.exceptions.base import AppBaseException
from app.core.settings import settings
from app.core.logging import logger


LOCK_EXPIRE = 25
IDEMPOTENCY_EXPIRE = 900  # ← FIX b


@shared_task(
    bind=True,
    autoretry_for=(RedisError, OperationalError),
    retry_kwargs={"max_retries": 3, "countdown": 2},
    retry_backoff=True,
)
def refresh_primary_token_task(
    self,
    refresh_token: str,
    old_access_token: str,
    ip: str,
    user_agent: str | None,
):
    db = SessionLocal()
    redis = RedisService()

    ua = normalize_ua(user_agent)
    rt_hash = refresh_token_hash(refresh_token)

    lock_key = f"lock:refresh:{rt_hash}"
    idem_key = f"idem:refresh:{rt_hash}"
    rt_key = f"rt:{rt_hash}"
    bl_rt_key = f"bl:rt:{rt_hash}"

    try:
        # ---------- IDEMPOTENCY ----------
        if redis_call(lambda: redis.get_key_sync(idem_key)):
            logger.info(
                "REFRESH_IDEMPOTENT_REPLAY",
                extra={"task_id": self.request.id},
            )
            return {"status": "IDEMPOTENT"}

        # ---------- LOCK ----------
        if not redis_call(lambda: redis.acquire_lock_sync(lock_key, LOCK_EXPIRE)):
            raise AppBaseException(429, {"error_code": "TRY_AGAIN_LATER"})

        raw = redis_call(lambda: redis.get_key_sync(rt_key))
        if not raw:
            raise InvalidRefreshTokenError()

        user_id_str, ua_hash = raw.decode().split(":")
        user = db.get(User, int(user_id_str))

        if not user or ua_hash != refresh_token_hash(ua):
            raise InvalidRefreshTokenError()

        # ---------- ROTATE ----------
        redis_call(lambda: redis.delete_sync(rt_key))
        redis_call(lambda: redis.set_key_sync(bl_rt_key, "1", expire=604800))

        # access token blacklist (اجباری)
        redis_call(lambda: redis.set_key_sync(
            f"bl:at:{refresh_token_hash(old_access_token)}",
            "1",
            expire=int(settings.ACCESS_TOKEN_EXPIRE.total_seconds()),
        ))

        access = create_access_token(str(user.id), user.role)
        new_refresh = create_refresh_token(str(user.id))

        redis_call(lambda: redis.set_key_sync(
            f"rt:{refresh_token_hash(new_refresh)}",
            f"{user.id}:{refresh_token_hash(ua)}",
            expire=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
        ))

        redis_call(lambda: redis.set_key_sync(
            idem_key,
            "1",
            expire=IDEMPOTENCY_EXPIRE,
        ))

        db.commit()

        AuditService.log(
            db=db,
            user_id=user.id,
            action="REFRESH_PRIMARY_SUCCESS",
            success=True,
            ip=ip,
            user_agent=ua,
        )

        logger.info(
            "REFRESH_PRIMARY_SUCCESS",
            extra={"task_id": self.request.id},
        )

        return {"status": "SUCCESS"}

    except InvalidRefreshTokenError:
        db.rollback()
        AuditService.log(
            db=db,
            user_id=None,  # ← عمداً بدون user_id
            action="REFRESH_PRIMARY_FAILED",
            success=False,
            ip=ip,
            user_agent=ua,
        )
        raise

    finally:
        redis_call(lambda: redis.release_lock_sync(lock_key))
        db.close()
