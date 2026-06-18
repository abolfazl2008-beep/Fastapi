from celery import shared_task
from sqlalchemy.exc import OperationalError
from smtplib import SMTPException
from app.db.session import SessionLocal
from app.models.user import User
from app.services.password_reset_service import PasswordResetService
from app.core.password import hash_password
from app.tasks.email_tasks import send_password_reset_email_task
from app.tasks.audit_tasks import audit_log_task
from app.core.settings import settings
from app.core.logging import logger


def _db_session():
    db = SessionLocal()
    db.execute(
        f"SET statement_timeout = '{settings.PASSWORD_RESET_DB_TIMEOUT_SECONDS}s'"
    )
    return db


@shared_task(
    bind=True,
    autoretry_for=(OperationalError, SMTPException),
    retry_kwargs={"max_retries": 3, "countdown": 3},
)
def password_reset_request_task(self, user_id: int, ip: str):
    db = _db_session()
    try:
        raw = PasswordResetService.create_token(db, user_id)

        send_password_reset_email_task.delay(
            user_id=user_id,
            token=raw,
        )

        audit_log_task.delay(
            user_id,
            "PASSWORD_RESET_REQUEST",
            True,
            {"ip": ip},
        )
    except Exception:
        logger.exception(
            "PASSWORD_RESET_REQUEST_FAILED",
            extra={"task_id": self.request.id},
        )
        raise
    finally:
        db.close()


@shared_task(
    bind=True,
    autoretry_for=(OperationalError,),
    retry_kwargs={"max_retries": 2, "countdown": 2},
)
def password_reset_confirm_task(self, raw_token: str, new_password: str, ip: str):
    db = _db_session()
    try:
        user_id = PasswordResetService.verify_and_consume(db, raw_token)

        user = db.get(User, user_id)
        if not user:
            raise ValueError("USER_NOT_FOUND")

        user.password_hash = hash_password(new_password)
        db.commit()

        audit_log_task.delay(
            user_id,
            "PASSWORD_RESET_CONFIRM_SUCCESS",
            True,
            {"ip": ip},
        )

        return {"status": "SUCCESS"}

    except Exception:
        db.rollback()
        audit_log_task.delay(
            None,
            "PASSWORD_RESET_CONFIRM_FAILED",
            False,
            {"ip": ip},
        )
        raise
    finally:
        db.close()
