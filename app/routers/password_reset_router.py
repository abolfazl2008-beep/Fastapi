from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.tasks.password_reset_tasks import (
    password_reset_request_task,
    password_reset_confirm_task,
)
from app.core.rate_limit import limiter
from app.core.security import safe_hash
from app.core.redis_service import RedisService
from app.core.exceptions.base import AppBaseException

router = APIRouter()


def reset_key_ip(request: Request):
    return f"pwdreset:ip:{safe_hash(request.client.host)}"


@router.post("/reset/request")
@limiter.limit("3/minute", key_func=reset_key_ip)
@limiter.limit("10/hour", key_func=reset_key_ip)
async def request_password_reset(
    email: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()

    if user:
        password_reset_request_task.delay(
            user_id=user.id,
            ip=request.client.host,
        )

    return {"message": "If the email exists, a reset link will be sent"}


@router.post("/reset/confirm")
@limiter.limit("5/15minutes")
async def confirm_password_reset(
    token: str,
    new_password: str,
    request: Request,
    redis: RedisService = Depends(),
):
    if len(token) < 50:
        raise AppBaseException(400, {"error_code": "INVALID_TOKEN_FORMAT"})

    if len(new_password) < 12:
        raise AppBaseException(400, {"error_code": "WEAK_PASSWORD"})

    token_key = f"pwdreset:token:{safe_hash(token)}"
    count = await redis.incr(token_key)
    if count == 1:
        await redis.expire(token_key, 900)
    if count > 5:
        raise AppBaseException(429, {"error_code": "TOO_MANY_ATTEMPTS"})

    job = password_reset_confirm_task.delay(
        raw_token=token,
        new_password=new_password,
        ip=request.client.host,
    )

    try:
        result = job.get(timeout=10)
    except Exception:
        raise AppBaseException(400, {"error_code": "INVALID_OR_EXPIRED_TOKEN"})

    if result.get("status") != "SUCCESS":
        raise AppBaseException(400, {"error_code": "INVALID_OR_EXPIRED_TOKEN"})

    return {"message": "Password reset successful"}
