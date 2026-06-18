
import asyncio
import json
from typing import List
from sqlalchemy.orm import Session
from redis.exceptions import RedisError
from app.core.logging import logger
from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.models.audit_log import AuditLog
from app.core.config import settings


APP_NAME = getattr(settings, "APP_NAME", "app")
AUDIT_QUEUE_KEY = f"audit:{APP_NAME}:queue"
AUDIT_DLQ_KEY = f"audit:{APP_NAME}:dlq"

BATCH_SIZE = 100
SLEEP_ON_EMPTY = 2


class AuditWorker:
    @staticmethod
    async def start():
        logger.info("AUDIT_WORKER_STARTED")
        while True:
            try:
                await AuditWorker._process_batch()
            except Exception:
                logger.exception("AUDIT_WORKER_CRASH")
                await asyncio.sleep(5)

    @staticmethod
    async def _process_batch():
        redis_conn = get_redis()

        items: List[str] = []
        try:
            for _ in range(BATCH_SIZE):
                item = await redis_conn.lpop(AUDIT_QUEUE_KEY)
                if not item:
                    break
                items.append(item)

            if not items:
                await asyncio.sleep(SLEEP_ON_EMPTY)
                return

            logs = [json.loads(i) for i in items]

            db: Session = SessionLocal()
            try:
                db.bulk_insert_mappings(AuditLog, logs)
                db.commit()
                logger.debug("AUDIT_BATCH_DB_WRITE_SUCCESS", extra={"count": len(logs)})
            except Exception:
                db.rollback()
                logger.exception("AUDIT_BATCH_DB_WRITE_FAIL")


                async with redis_conn.pipeline(transaction=True) as pipe:
                    for raw in items:
                        pipe.rpush(AUDIT_DLQ_KEY, raw)
                    pipe.ltrim(AUDIT_DLQ_KEY, -1000, -1)
                    pipe.expire(AUDIT_DLQ_KEY, 86400 * 30)
                    await pipe.execute()
            finally:
                db.close()

        except RedisError:
            logger.exception("AUDIT_WORKER_REDIS_ERROR")
            await asyncio.sleep(5)


async def dlq_worker():
    redis = await get_redis()

    while True:
        raw = await redis.lpop(AUDIT_DLQ_KEY)
        if not raw:
            await asyncio.sleep(5)
            continue

        db = SessionLocal()
        try:
            db.add(AuditLog(**json.loads(raw)))
            db.commit()
            logger.info("AUDIT_DLQ_RECOVERED")
        except Exception:
            db.rollback()
            logger.exception("AUDIT_DLQ_STILL_FAILING")
        finally:
            db.close()
