from celery import Celery
from app.core.settings import settings

celery_app = Celery(
    "audit_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.task_routes = {
    "app.tasks.audit.audit_log_task": {"queue": "audit"},
}

celery_app.conf.update(
    task_acks_late=False,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,

    task_default_queue="audit",
    task_queues={
        "audit": {
            "exchange": "audit",
            "routing_key": "audit",
        }
    },
    task_routes={
        "app.tasks.audit.audit_log_task": {"queue": "audit"},
    },
    timezone="UTC",
    enable_utc=True,
)


celery_app.autodiscover_tasks(["app.tasks"])
