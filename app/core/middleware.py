import json
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from jose import jwt, JWTError, ExpiredSignatureError
from app.core.settings import settings
from app.core.ip import get_real_ip
from app.core.logging import logger
from typing import Awaitable, Callable


PUBLIC_PATHS = {
    "/auth/login",
    "/auth/refresh",
    "/auth/register",
    "/auth/logout",
    "/auth/verify-email",
    "/health",
    "/docs",
    "/openapi.json",
}

async def auth_middleware(request: Request, call_next: Callable) -> Awaitable:
    request.state.user_id = None
    request.state.role = "anonymous"

    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid Authorization header"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": False,
                "verify_iss": True,
                "verify_aud": True,
                "verify_alg": True,
                "require": ["exp", "iat", "sub", "jti"],
            },
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )

        user_id = payload.get("sub")
        if not user_id:
            raise JWTError("Missing sub claim")

        request.state.user_id = str(user_id)
        request.state.role = payload.get("role", "user")


        logger.info("JWT authenticated", extra={"user_id": user_id, "ip": get_real_ip(request)})

    except ExpiredSignatureError:
        return JSONResponse(
            status_code=401,
            content={"detail": "Token has expired"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        logger.warning(
            "JWT verification failed",
            extra={"error": str(e), "ip": get_real_ip(request)},
            exc_info=True,
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await call_next(request)


async def password_reset_context_middleware(request: Request, call_next: Callable) -> Awaitable:
    request.state.email_for_rate_limit = None
    body_bytes = b""

    if request.url.path == "/password/reset/request" and request.method == "POST":
        content_type = request.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body = json.loads(body_bytes)
                    email = body.get("email")
                    if isinstance(email, str):
                        request.state.email_for_rate_limit = email.lower().strip()
            except json.JSONDecodeError:
                logger.debug("Invalid JSON in password reset request", extra={"ip": get_real_ip(request)})
            except Exception as e:
                logger.warning("Failed to parse email for rate-limit", extra={"error": str(e)})
            finally:
                request._body = body_bytes

    return await call_next(request)
