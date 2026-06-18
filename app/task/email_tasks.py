from celery import shared_task
from app.db.session import SessionLocal
from app.services.password_reset_service import PasswordResetService
from app.models.user import User
from app.core.email import send_email
from asgiref.sync import async_to_sync


@shared_task(bind=True, max_retries=3, soft_time_limit=30)
def send_password_reset_email_task(self, user_id: int):
    try:
        with SessionLocal() as db:
            raw_token = PasswordResetService.create_token_record(db, user_id)
            user = db.query(User).get(user_id)

        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"

        async_to_sync(send_email)(
            to=[user.email],
            subject="Password Reset",
            body=f"Click to reset: {reset_link}",
        )

    except Exception as exc:
        raise self.retry(exc=exc, countdown=10 * (2 ** self.request.retries))
