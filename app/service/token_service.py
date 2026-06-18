from celery.result import AsyncResult
from celery.exceptions import OperationalError as CeleryOperationalError
from kombu.exceptions import OperationalError as KombuOperationalError  # اگر kombu مستقیم استفاده می‌کنی
from app.tasks.auth.refresh_primary_token_task import refresh_primary_token_task
from app.core.exceptions.base import AppBaseException
from app.core.logging import logger

class AuthRefreshService:
    @staticmethod
    def refresh_primary_async(
        *,
        refresh_token: str,
        old_access_token: str,
        ip: str,
        user_agent: str | None = None,
    ) -> AsyncResult:
        try:
            task: AsyncResult = refresh_primary_token_task.delay(
                refresh_token=refresh_token,
                old_access_token=old_access_token,
                ip=ip,
                user_agent=user_agent,
            )

            logger.info(
                "REFRESH_TASK_ENQUEUED_SUCCESS",
                extra={
                    "task_id": task.id,
                    "ip": ip,
                    "user_agent_snippet": (user_agent or "unknown")[:50],
                    "refresh_token_hash": refresh_token_hash(refresh_token)[:16] + "...",
                }
            )
            return task

        except (CeleryOperationalError, KombuOperationalError) as e:
            # Broker (Redis/RabbitMQ) down, connection timeout, etc.
            logger.error(
                "CELERY_BROKER_UNAVAILABLE",
                extra={"error": str(e), "ip": ip},
                exc_info=True
            )
            raise AppBaseException(
                status_code=503,
                detail={
                    "error_code": "QUEUE_UNAVAILABLE",
                    "message": "Task queue is temporarily unavailable. Please try again shortly."
                }
            )

        except TypeError as e:
            logger.error(
                "CELERY_TASK_SERIALIZATION_FAILED",
                extra={"error": str(e), "ip": ip},
                exc_info=True
            )
            raise AppBaseException(
                status_code=500,
                detail={
                    "error_code": "INVALID_TASK_PARAMS",
                    "message": "Internal error preparing refresh task."
                }
            )

        except Exception as exc:
            logger.exception(
                "REFRESH_ENQUEUE_CRITICAL_FAILURE",
                extra={
                    "ip": ip,
                    "user_agent": user_agent,
                    "refresh_token_prefix": refresh_token[:8] + "..." if refresh_token else "none",
                }
            )
            raise AppBaseException(
                status_code=500,
                detail={
                    "error_code": "TOKEN_REFRESH_ENQUEUE_FAILED",
                    "message": "Failed to queue token refresh. Contact support if persists."
                }
            )
