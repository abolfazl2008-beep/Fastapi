from typing import Optional, Any
from redis.asyncio import Redis
from app.core.logging import logger
import asyncio
import uuid
from fastapi import Depends
from app.core.redis import get_redis

class RedisService:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def set_key(self, key: str, value: Any, expire: Optional[int] = None):
        try:
            await self.redis.set(key, value, ex=expire)
            logger.debug(f"Redis SET key={key} (expire={expire})")
        except Exception as e:
            logger.error(f"Redis SET failed key={key}", exc_info=True)
            raise

    async def get_key(self, key: str) -> Optional[Any]:
        try:
            value = await self.redis.get(key)
            logger.debug(f"Redis GET key={key}")
            return value
        except Exception as e:
            logger.error(f"Redis GET failed key={key}", exc_info=True)
            raise

    async def increment(self, key: str, expire: Optional[int] = None) -> int:
        try:
            value = await self.redis.incr(key)
            if expire:
                # همیشه expire ست شود
                await self.redis.expire(key, expire)
            logger.debug(f"Redis INCR key={key} → incremented")
            return value
        except Exception as e:
            logger.error(f"Redis INCR failed key={key}", exc_info=True)
            raise

    async def acquire_lock(self, key: str, expire: int = 10) -> Optional[str]:
        lock_id = str(uuid.uuid4())
        try:
            result = await self.redis.set(key, lock_id, ex=expire, nx=True)
            logger.debug(f"Redis LOCK key={key} → {result}")
            return lock_id if result else None
        except Exception as e:
            logger.error(f"Redis LOCK failed key={key}", exc_info=True)
            raise

    async def release_lock(self, key: str, lock_id: Optional[str] = None):
        try:
            if lock_id:
                script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                deleted = await self.redis.eval(script, 1, key, lock_id)
            else:
                deleted = await self.redis.delete(key)
            logger.debug(f"Redis UNLOCK key={key} → deleted={deleted}")
        except Exception as e:
            logger.error(f"Redis UNLOCK failed key={key}", exc_info=True)
            raise


async def get_redis_service(redis: Redis = Depends(get_redis)) -> RedisService:
    return RedisService(redis)
