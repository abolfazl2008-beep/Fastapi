from fastapi import APIRouter, Depends, Request, Cookie, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.dependencies import get_db
from app.dependencies.redis import get_redis
from app.core.redis_service import RedisService
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.auth_service import (
    login_service,
    refresh_tokens_service,
    logout_service,
)
from app.utils.network import get_real_ip
from app.services.auth_refresh_service import AuthRefreshService
from app.core.redis_service import RedisService
from app.core.security import hash_refresh_token
from app.core.exceptions.base import AppBaseException


router = APIRouter(prefix="/auth",tags=["auth"])


@router.post("/token/refresh", status_code=202)
async def refresh_token(
    request: Request,
    redis: RedisService = Depends(),
):
    try:
        body = await request.json()
    except Exception:
        raise AppBaseException(400, {"error_code": "INVALID_JSON"})

    refresh_token = body.get("refresh_token")
    old_access_token = body.get("access_token")

    if not refresh_token or not old_access_token:
        raise AppBaseException(400, {"error_code": "TOKENS_REQUIRED"})

    if len(refresh_token) < 20 or len(old_access_token) < 20:
        raise AppBaseException(400, {"error_code": "INVALID_TOKEN_FORMAT"})

    ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")


    rl_key = f"rl:refresh:ip:{hash_refresh_token(ip)}"
    count = await redis.incr(rl_key)
    if count == 1:
        await redis.expire(rl_key, 60)
    if count > 50:
        raise AppBaseException(429, {"error_code": "RATE_LIMITED"})

    try:
        task = AuthRefreshService.refresh_primary_async(
            refresh_token=refresh_token,
            old_access_token=old_access_token,
            ip=ip,
            user_agent=user_agent,
        )

        logger.info(
            "REFRESH_TOKEN_ENQUEUED",
            extra={
                "task_id": task.id,
                "ip": ip,
                "user_agent": user_agent[:100],
                "refresh_hash": hash_refresh_token(refresh_token)[:16] + "...",
            }
        )
        return JSONResponse(
            status_code=202,
            content={
                "status": "ACCEPTED",
                "task_id": task.id,
            }
        )
    except (CeleryOperationalError, KombuOperationalError) as e:
        logger.error("CELERY_BROKER_DOWN", extra={"error": str(e), "ip": ip}, exc_info=True)
        raise AppBaseException(
            503,
            {"error_code": "QUEUE_UNAVAILABLE", "message": "Service temporarily unavailable, try later"}
        )
    except Exception as exc:
        logger.exception(
            "REFRESH_ENQUEUE_FAILED",
            extra={"ip": ip, "refresh_prefix": refresh_token[:8] + "..."}
        )
        raise AppBaseException(
            500,
            {"error_code": "REFRESH_QUEUED_FAILED", "message": "Failed to process refresh request"}
        )


@router.post("/refresh")
async def refresh_token_endpoint(
    request: Request,
    refresh_token: str = Cookie(None, alias=REFRESH_COOKIE_NAME),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_async_db),
    redis: RedisService = Depends(get_redis_service),
):
    if not refresh_token:
        raise AppBaseException(401, {"error_code": "NO_REFRESH_TOKEN"})

    ip = get_real_ip(request) or "unknown"
    ua = request.headers.get("user-agent", "unknown")
    request_id = request.headers.get("x-request-id")

    old_access_token = (
        authorization.split(" ")[1]
        if authorization and authorization.startswith("Bearer ")
        else None
    )

    access, new_refresh = await auth_service.refresh_tokens(
        refresh_token=refresh_token,
        db=db,
        ip=ip,
        user_agent=ua,
        redis=redis,
        old_access_token=old_access_token,
        request_id=request_id,
    )

    response = JSONResponse({"access_token": access, "token_type": "bearer"})

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=new_refresh,
        max_age=int(settings.REFRESH_TOKEN_EXPIRE.total_seconds()),
        httponly=True,
        secure=settings.ENV == "production",
        samesite="strict",
        path="/",
    )
    return response

@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisService = Depends(get_redis),
):
    ip = get_real_ip(request) or "unknown"
    ua = request.headers.get("user-agent")
    req_id = request.headers.get("x-request-id")

    access, refresh = await login_service(
        db=db,
        redis=redis,
        identifier=payload.identifier,
        password=payload.password,
        ip=ip,
        user_agent=ua,
        request_id=req_id,
    )

    response = TokenResponse(access_token=access)
    response.set_refresh_cookie(refresh)
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    refresh_token: str = Cookie(...),
    db: AsyncSession = Depends(get_db),
    redis: RedisService = Depends(get_redis),
):
    ip = get_real_ip(request) or "unknown"
    ua = request.headers.get("user-agent")
    req_id = request.headers.get("x-request-id")

    access, new_refresh = await refresh_tokens_service(
        db=db,
        redis=redis,
        refresh_token=refresh_token,
        ip=ip,
        user_agent=ua,
        request_id=req_id,
    )

    response = TokenResponse(access_token=access)
    response.set_refresh_cookie(new_refresh)
    return response


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    refresh_token: str | None = Cookie(None),
    authorization: str | None = Header(None),
    redis: RedisService = Depends(get_redis),
):
    ip = get_real_ip(request) or "unknown"
    ua = request.headers.get("user-agent")
    req_id = request.headers.get("x-request-id")

    access = (
        authorization.split(" ")[1]
        if authorization and authorization.startswith("Bearer ")
        else None
    )

    await logout_service(
        redis=redis,
        refresh_token=refresh_token,
        access_token=access,
        ip=ip,
        user_agent=ua,
        request_id=req_id,
    )

    return Response(status_code=204)

