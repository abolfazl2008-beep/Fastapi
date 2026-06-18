from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from app.core.security import decode_token
from app.utils.enums import RoleEnum
from app.core.rate_limit import limiter
from app.api.v1.mfa.limits import mfa_user_key
from app.core.ip import get_real_ip
from app.core.exceptions.base import AppBaseException

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2)):
    payload = decode_token(token)
    if not payload or payload["type"] != "access":
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


def require_active_verified_user(user=Depends(get_current_user)):
    if not user.is_active:
        raise AppBaseException(403, {"error_code": "USER_INACTIVE"})
    if user.locked:
        raise AppBaseException(403, {"error_code": "USER_LOCKED"})
    if not user.email_verified:
        raise AppBaseException(403, {"error_code": "EMAIL_NOT_VERIFIED"})
    return user

def require_admin(user=Depends(get_current_user)):
    if user["role"] != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def mfa_rate_limit():
    def decorator(func):
        func = limiter.limit("5/minute", key_func=mfa_user_key)(func)
        func = limiter.limit("10/minute", key_func=lambda r: f"ip:{get_real_ip(r)}")(func)
        func = limiter.limit("200/hour", key_func=lambda _: "global:mfa")(func)
        return func
    return decorator
