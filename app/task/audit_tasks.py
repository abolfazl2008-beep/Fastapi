from celery import shared_task
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.audit_log import AuditLog
from app.core.settings import settings
from app.core.logging import logger


def sanitize_user_agent(ua: str | None) -> str:
    ua = (ua or "unknown")[: settings.MAX_USER_AGENT_LENGTH]
    return ua.encode("ascii", "ignore").decode("ascii")


def sanitize_metadata(metadata: dict | None) -> dict:
    if not metadata:
        return {}
    safe = {}
    for i, (k, v) in enumerate(metadata.items()):
        if i >= settings.MAX_METADATA_KEYS:
            break
        safe[str(k)[:50]] = str(v)[: settings.MAX_METADATA_VALUE_LENGTH]
    return safe


@shared_task(
    bind=True,
    autoretry_for=(SQLAlchemyError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def audit_log_task(
    self,
    *,
    fingerprint: str,
    action: str,
    success: bool,
    user_id: str | None,
    ip: str,
    user_agent: str | None,
    request_id: str | None = None,
    metadata: dict | None = None,
    event_time: str,
):
    session: Session = SessionLocal()
    try:
        ua_safe = sanitize_user_agent(user_agent)
        meta_safe = sanitize_metadata(metadata)

        try:
            created_at = datetime.fromisoformat(event_time)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except ValueError:
            created_at = datetime.now(timezone.utc)

        user_id_safe = user_id

        audit = AuditLog(
            id=str(uuid4()),
            fingerprint=fingerprint,
            created_at=created_at,
            action=action,
            success=success,
            user_id=user_id_safe,
            ip=ip,
            user_agent=ua_safe,
            request_id=request_id,
            metadata=meta_safe,
        )

        session.add(audit)
        session.commit()

    except IntegrityError as exc:
        session.rollback()
        if "ux_audit_fingerprint" in str(exc.orig):
            logger.info("AUDIT_DUPLICATE_SKIPPED_DB", extra={"fingerprint": fingerprint})
            return
        else:
            logger.error("AUDIT_INTEGRITY_OTHER", exc_info=True)
            raise self.retry(exc=exc)

    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("AUDIT_DB_ERROR", exc_info=True)
        raise self.retry(exc=exc)

    finally:
        session.close()
