
import hashlib
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from app.core.ip import get_real_ip
from app.core.logging import logger
from app.core.settings import settings
from app.core.redis import build_redis_url
from app.utils.rate_limits import SALT,normalize_ip,safe_hash,_build_key


KEY_VERSION = getattr(settings, "VERSION", "v1")



def global_rate_key(request: Request) -> str:
    ip = _normalize_ip(get_real_ip(request))
    user = getattr(request.state, "user", None)
    if user and getattr(user, "id", None) is not None:
        prefix = "staff" if getattr(user, "role", "") in ("admin", "support") else "user"
        base = f"{prefix}:{user.id}"
    else:
        base = f"ip:{ip}"
    return _build_key(base, "global")


def mfa_rate_limit_key(request: Request) -> str:
    ip = _normalize_ip(get_real_ip(request))
    user = getattr(request.state, "user", None)
    if user and getattr(user, "id", None) is not None:
        base = f"mfa:{user.id}:{ip}"
    else:
        logger.debug("MFA rate-limit called without authenticated user", extra={"ip": ip})
        base = f"mfa:anon:{ip}"
    return _build_key(base, "mfa")


def password_reset_email_ip_key(request: Request, email: str) -> str:
    ip = _normalize_ip(get_real_ip(request))
    email_clean = (email or "").lower().strip()
    base = f"email:{email_clean}:{ip}" if email_clean else f"ip:{ip}"
    return _build_key(base, "pwd_reset")


def password_reset_daily_key(request: Request, email: str) -> str:
    ip = _normalize_ip(get_real_ip(request))
    email_clean = (email or "").lower().strip()
    base = f"daily:{email_clean}:{ip}" if email_clean else f"ip:{ip}"
    return _build_key(base, "pwd_reset_daily")


def reset_confirm_token_key(request: Request, token: str) -> str:
    base = f"token:{token or 'unknown'}"
    return _build_key(base, "pwd_confirm_token")


def reset_confirm_ip_key(request: Request) -> str:
    ip = _normalize_ip(get_real_ip(request))
    base = f"ip:{ip}"
    return _build_key(base, "pwd_confirm_ip")


limiter = Limiter(
    key_func=global_rate_key,
    storage_uri=build_redis_url(),
    default_limits=None,
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    retry_after = getattr(exc, "retry_after", 60)
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None) if user else None
    role = getattr(user, "role", "anonymous") if user else "anonymous"
    ip = _normalize_ip(get_real_ip(request))

    logger.warning(
        "RATE_LIMIT_EXCEEDED",
        extra={
            "path": str(request.url.path),
            "method": request.method,
            "user_id": user_id,
            "role": role,
            "ip": ip,
            "retry_after": retry_after,
            "limit_key": getattr(exc, "limit_key", "unknown"),
        }
    )
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
        headers={"Retry-After": str(retry_after)},
    )
