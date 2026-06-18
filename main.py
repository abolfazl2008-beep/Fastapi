from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from app.core.redis_service import create_redis
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.cors import setup_cors
from app.core.exceptions.handlers import register_exception_handlers
from app.core.middleware.auth import AuthMiddleware
from app.core.middleware.logging import LoggingMiddleware
from app.core.middleware.password_reset import PasswordResetContextMiddleware
from app.routers import auth, users, posts, mfa, password_reset_router, email_service
from app.workers.audit_worker import AuditWorker
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = await create_redis()
    app.state.redis = redis_client
    app.state.redis_pool = getattr(redis_client, "_pool", None)
    audit_task = asyncio.create_task(AuditWorker.start(), name="audit_worker")
    app.state.audit_task = audit_task

    yield

    if hasattr(app.state, "audit_task"):
        app.state.audit_task.cancel()
        try:
            await app.state.audit_task
        except asyncio.CancelledError:
            pass


    if hasattr(app.state, "redis"):
        await app.state.redis.aclose()
    if hasattr(app.state, "redis_pool") and app.state.redis_pool:
        await app.state.redis_pool.disconnect()


    await asyncio.to_thread(logger.info, "App shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Bank API",
        description="Secure Banking API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )


    app.state.limiter = limiter
    setup_cors(app)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(PasswordResetContextMiddleware)
    register_exception_handlers(app)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(posts.router)
    app.include_router(mfa.router)
    app.include_router(password_reset_router.router)
    app.include_router(email_service.router)

    return app



app = create_app()
