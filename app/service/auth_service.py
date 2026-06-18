from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.core.security import create_access_token, create_refresh_token
from app.core.settings import settings
from app.core.redis_service import RedisService
from app.core.exceptions import AppBaseException
from app.core.exceptions.auth import InvalidCredentialsError, InvalidRefreshTokenError
from app.tasks.audit import audit_log_task
from app.utils.rate_limits import safe_hash


async def _rate_limit(redis: RedisService, key: str, limit: int, window: int):
    count = await redis.increment(key, expire=window)
    if count > limit:
        raise AppBaseException(
            429,
            {"error_code": "RATE_LIMIT_EXCEEDED"},
            headers={"Retry-After": str(window)},
        )


# ---------- LOGIN ----------

async def login_service(
    *,
    db: AsyncSession,
    redis: RedisService,
    identifier: str,
    password: str,
    ip: str,
    user_agent: str,
    request_id: Optional[str],
) -> Tuple[str, str]:
    ua = user_agent or "unknown"
    event_time = datetime.now(timezone.utc).isoformat()

    await _rate_limit(
        redis,
        f"rl:login:ip:{safe_hash(ip)}",
        settings.LOGIN_IP_LIMIT,
        settings.LOGIN_IP_WINDOW,
    )

    user = await User.authenticate(db, identifier, password)

    if user:
        await _rate_limit(
            redis,
            f"rl:login:user:{safe_hash(str(user.id))}:{safe_hash(ip)}",
            settings.LOGIN_USER_LIMIT,
            settings.LOGIN_USER_WINDOW,
        )

    if not user:
        audit_log_task.apply_async(
            queue="audit",
            kwargs={
                "fingerprint": f"login:{safe_hash(identifier)}:{event_time}:fail",
                "action": "LOGIN_FAILED",
                "success": False,
                "user_id": None,
                "ip": ip,
                "user_agent": ua,
                "request_id": request_id,
                "metadata": {},
                "event_time": event_time,
            },
        )
        raise InvalidCredentialsError()

    access = create_access_token(str(user.id), user.role)
    refresh = create_refresh_token(str(user.id))

    await redis.set_key(
        f"rt:{safe_hash(refresh)}",
        f"{user.id}:{safe_hash(ua)}",
        expire=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
    )

    audit_log_task.apply_async(
        queue="audit",
        kwargs={
            "fingerprint": f"login:{safe_hash(str(user.id))}:{event_time}:success",
            "action": "LOGIN_SUCCESS",
            "success": True,
            "user_id": str(user.id),
            "ip": ip,
            "user_agent": ua,
            "request_id": request_id,
            "metadata": {},
            "event_time": event_time,
        },
    )

    return access, refresh


# ---------- REFRESH ----------

async def refresh_tokens_service(
    *,
    db: AsyncSession,
    redis: RedisService,
    refresh_token: str,
    ip: str,
    user_agent: str,
    request_id: Optional[str],
) -> Tuple[str, str]:
    ua = user_agent or "unknown"
    event_time = datetime.now(timezone.utc).isoformat()

    await _rate_limit(redis, f"rl:refresh:ip:{safe_hash(ip)}", 50, 60)

    raw = await redis.get_key(f"rt:{safe_hash(refresh_token)}")
    if not raw:
        raise InvalidRefreshTokenError()

    user_id_raw, ua_hash = raw.split(":")

    try:
        user_id = int(user_id_raw)
    except Exception:
        raise InvalidRefreshTokenError()

    await _rate_limit(
        redis,
        f"rl:refresh:user:{safe_hash(str(user_id))}",
        settings.REFRESH_LIMIT,
        settings.REFRESH_WINDOW,
    )

    if ua_hash != safe_hash(ua):
        raise InvalidRefreshTokenError()

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise InvalidRefreshTokenError()

    await redis.delete(f"rt:{safe_hash(refresh_token)}")

    access = create_access_token(str(user.id), user.role)
    new_refresh = create_refresh_token(str(user.id))

    await redis.set_key(
        f"rt:{safe_hash(new_refresh)}",
        f"{user.id}:{safe_hash(ua)}",
        expire=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
    )

    audit_log_task.apply_async(
        queue="audit",
        kwargs={
            "fingerprint": f"refresh:{safe_hash(refresh_token)}:{event_time}:success",
            "action": "REFRESH_SUCCESS",
            "success": True,
            "user_id": str(user.id),
            "ip": ip,
            "user_agent": ua,
            "request_id": request_id,
            "metadata": {},
            "event_time": event_time,
        },
    )

    return access, new_refresh


# ---------- LOGOUT ----------

async def logout_service(
    *,
    redis: RedisService,
    refresh_token: Optional[str],
    access_token: Optional[str],
    ip: str,
    user_agent: str,
    request_id: Optional[str],
):
    event_time = datetime.now(timezone.utc).isoformat()

    if refresh_token:
        await redis.set_key(
            f"bl:rt:{safe_hash(refresh_token)}",
            "1",
            expire=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
        )

    if access_token:
        await redis.set_key(
            f"bl:at:{safe_hash(access_token)}",
            "1",
            expire=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        )

    audit_log_task.apply_async(
        queue="audit",
        kwargs={
            "fingerprint": f"logout:{safe_hash(access_token or 'na')}:{event_time}:success",
            "action": "LOGOUT",
            "success": True,
            "user_id": None,
            "ip": ip,
            "user_agent": user_agent or "unknown",
            "request_id": request_id,
            "metadata": {},
            "event_time": event_time,
        },
    )
