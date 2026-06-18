import asyncio
from redis.asyncio import Redis, ConnectionPool
from app.core.settings import settings
from app.core.logging import logger
from typing import Optional

# Global Redis client & pool
REDIS_POOL: Optional[ConnectionPool] = None
REDIS_CLIENT: Optional[Redis] = None


def build_redis_url(db: int) -> str:
    scheme = "rediss" if getattr(settings, "REDIS_SSL", False) else "redis"
    auth = f":{settings.REDIS_PASSWORD}@" if getattr(settings, "REDIS_PASSWORD", None) else ""

    if not getattr(settings, "REDIS_HOST", None):
        raise ValueError("REDIS_HOST is not set in settings")
    if not getattr(settings, "REDIS_PORT", None):
        raise ValueError("REDIS_PORT is not set in settings")

    return f"{scheme}://{auth}{settings.REDIS_HOST}:{settings.REDIS_PORT}/{db}"


async def init_redis_pool(
    db: int = None,
    max_connections: int = None,
    retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 16.0,
) -> Redis:

    global REDIS_POOL, REDIS_CLIENT
    db = db or settings.REDIS_DB_RATE_LIMIT
    max_connections = max_connections or getattr(settings, "REDIS_MAX_CONN", 50)

    REDIS_POOL = ConnectionPool.from_url(
        build_redis_url(db),
        decode_responses=True,
        max_connections=max_connections,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True,
        health_check_interval=15,
    )

    REDIS_CLIENT = Redis(connection_pool=REDIS_POOL)

    delay = initial_delay
    last_exception = None

    for attempt in range(retries):
        try:
            await REDIS_CLIENT.ping()
            logger.info(f"Redis connected successfully (attempt {attempt+1}/{retries})")
            return REDIS_CLIENT
        except Exception as e:
            last_exception = e
            logger.warning(f"Redis connection attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
            else:
                # Ensure pool disconnected on final failure
                if REDIS_POOL:
                    await REDIS_POOL.disconnect()
                    REDIS_POOL = None
                REDIS_CLIENT = None
                logger.critical(f"Redis unavailable after {retries} attempts: {e}")
                raise RuntimeError(f"Redis unavailable after {retries} attempts: {e}") from e

    # Should not reach here
    raise RuntimeError(f"Redis initialization failed unexpectedly: {last_exception}")


async def shutdown_redis():
    """
    Properly shutdown Redis global pool
    """
    global REDIS_CLIENT, REDIS_POOL
    if REDIS_CLIENT:
        await REDIS_CLIENT.close()
        REDIS_CLIENT = None
    if REDIS_POOL:
        await REDIS_POOL.disconnect()
        REDIS_POOL = None
    logger.info("Redis connection pool closed.")


async def get_redis() -> Redis:
    """
    Return the global Redis client. Async function.
    """
    if not REDIS_CLIENT:
        raise RuntimeError("Redis client not initialized. Call init_redis_pool first.")
    return REDIS_CLIENT
