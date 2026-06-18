import ipaddress
import hashlib
import hmac
import time
import random
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from app.core.ip import get_real_ip
from app.core.logging import logger
from app.core.settings import settings
from app.core.redis import build_redis_url



KEY_VERSION = getattr(settings, "VERSION", "v1")
SAFE_HASH_KEY = b"fixed_secret_key_for_hmac"
PREFIX_FIXED = "rl:"



def _normalize_ip(ip: str) -> str:
    try:
        if not ip:
            return f"unknown:empty"
        ip = ip.split('%')[0]
        ip_obj = ipaddress.ip_address(ip)
        if isinstance(ip_obj, ipaddress.IPv4Address):
            return str(ipaddress.IPv4Network(f"{ip}/24", strict=False).network_address)
        if isinstance(ip_obj, ipaddress.IPv6Address):
            return str(ipaddress.IPv6Network(f"{ip}/64", strict=False).network_address)
    except Exception:
        suffix = random.randint(0, 9999)
        return f"unknown:{suffix}:{int(time.time())}"

    return f"unknown:{ip}"


def safe_hash(value: str) -> str:
    value = (value or "").lower().strip()
    return hmac.new(SAFE_HASH_KEY, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _build_key(base: str, prefix: str) -> str:
    salt = b"rl_fixed_salt_for_hmac"
    raw = f"{prefix}:{base}:{KEY_VERSION}"
    return PREFIX_FIXED + hmac.new(salt, raw.encode("utf-8"), hashlib.sha256).hexdigest()[:40]




def global_rate_key(request: Request) -> str:
    ip = _normalize_ip(get_real_ip(request))
    user = getattr(request.state, "user", None)
    if user and getattr(user, "id", None) is not None:
        prefix = "staff" if getattr(user, "role", "") in ("admin", "support") else "user"
        base = f"{prefix}:{user.id}:{ip}"
    else:
        base = f"anon:{ip}"
    return _build_key(base, "global")


def mfa_rate_limit_key(request: Request) -> str:
    ip = _normalize_ip(get_real_ip(request))
    user = getattr(request.state, "user", None)
    if user and getattr(user, "id", None) is not None:
        base = f"mfa:{user.id}:{ip}"
    else:
        logger.debug("MFA rate-limit without authenticated user", extra={"ip": ip})
        base = f"mfa:anon:{ip}"
    return _build_key(base, "mfa")


def password_reset_email_ip_key(request: Request, email: str) -> str:
    ip = _normalize_ip(get_real_ip(request))
    email_clean = (email or "").lower().strip()
    if email_clean:
        base = f"email:{safe_hash(email_clean)}:{ip}"
    else:
        base = f"ip_only_strict:{ip}"
    return _build_key(base, "pwd_reset")


def password_reset_daily_key(request: Request, email: str) -> str:
    ip = _normalize_ip(get_real_ip(request))
    email_clean = (email or "").lower().strip()
    if email_clean:
        base = f"daily:{safe_hash(email_clean)}:{ip}"
    else:
        base = f"daily_ip_only:{ip}"
    return _build_key(base, "pwd_reset_daily")


def reset_confirm_token_key(request: Request, token: str) -> str:
    ip = _normalize_ip(get_real_ip(request))
    token_hash = safe_hash(token or "unknown")
    base = f"token:{token_hash}:{ip}"
    return _build_key(base, "pwd_confirm_token")


def reset_confirm_ip_key(request: Request) -> str:
    ip = _normalize_ip(get_real_ip(request))
    base = f"ip:{ip}"
    return _build_key(base, "pwd_confirm_ip")


def reset_confirm_global_ip_key(request: Request) -> str:
    ip = _normalize_ip(get_real_ip(request))
    base = f"global:{ip}"
    return _build_key(base, "pwd_confirm_global")




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
