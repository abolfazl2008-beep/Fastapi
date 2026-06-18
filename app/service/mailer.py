import asyncio
import random
import json
from datetime import datetime
from typing import List, Optional
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr, make_msgid
from email.header import Header
import aiosmtplib
from celery import shared_task
from app.core.settings import settings
from app.core.logging import logger
from app.core.exceptions.base import AppBaseException
from app.models.user import User
from app.services.audit_service import AuditService
from app.utils.email_utils import mask_email
from app.core.redis import get_redis

MAX_RECIPIENTS = 50
MAX_SUBJECT_LENGTH = 998
MAX_METADATA_LENGTH = 500
MAX_BODY_SIZE = 2_000_000
MAX_HTML_SIZE = 5_000_000


def _sanitize_header(value: Optional[str]) -> str:
    return str(Header(value, "utf-8")) if value else ""


def _validate_email_address(email: str) -> str:
    _, addr = parseaddr(email)
    if not addr or "@" not in addr:
        raise AppBaseException(
            400,
            {"message": f"Invalid email address: {email}", "error_code": "EMAIL_INVALID_RECIPIENT"},
        )
    return addr


def _truncate_str(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


@shared_task(bind=True, max_retries=3, soft_time_limit=60)
def send_email_task(
    to: List[str],
    subject: str,
    body: str,
    html: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    user_email: Optional[str] = None,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    """
    Celery task برای ارسال ایمیل به صورت async-safe و بدون singleton
    """
    async def _send_email():
        # Validate recipients and body size
        total_recipients = len(to) + len(cc or []) + len(bcc or [])
        if total_recipients == 0:
            raise AppBaseException(400, {"message": "No recipients", "error_code": "EMPTY_RECIPIENTS"})
        if total_recipients > MAX_RECIPIENTS:
            raise AppBaseException(400, {"message": f"Too many recipients, max {MAX_RECIPIENTS}", "error_code": "EMAIL_TOO_MANY_RECIPIENTS"})
        if len(subject) > MAX_SUBJECT_LENGTH:
            subject_truncated = subject[:MAX_SUBJECT_LENGTH]
        else:
            subject_truncated = subject
        if len(body) > MAX_BODY_SIZE or (html and len(html) > MAX_HTML_SIZE):
            raise AppBaseException(413, {"message": "Email too large", "error_code": "EMAIL_TOO_LARGE"})

        to_addrs = [_validate_email_address(addr) for addr in to]
        cc_addrs = [_validate_email_address(addr) for addr in (cc or [])]
        bcc_addrs = [_validate_email_address(addr) for addr in (bcc or [])]
        reply_to_addr = _validate_email_address(reply_to) if reply_to else None
        subject_sanitized = _sanitize_header(subject_truncated)

        # From
        from_email = getattr(settings, "SMTP_FROM_USER", None)
        from_name = getattr(settings, "SMTP_FROM_NAME", "No-Reply")
        if not from_email:
            raise AppBaseException(500, {"message": "SMTP_FROM_USER not configured", "error_code": "EMAIL_CONFIG_ERROR"})
        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((str(Header(from_name, "utf-8")), from_email))
        msg["To"] = ", ".join(to_addrs)
        if cc_addrs:
            msg["Cc"] = ", ".join(cc_addrs)
        if reply_to_addr:
            msg["Reply-To"] = reply_to_addr
        msg["Subject"] = subject_sanitized
        msg["Message-ID"] = make_msgid(domain=settings.SMTP_HOST.split(":")[0])
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))

        all_recipients = to_addrs + cc_addrs + bcc_addrs
        max_retries = getattr(settings, "SMTP_MAX_RETRIES", 3)
        max_delay = getattr(settings, "SMTP_MAX_DELAY", 60)
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                smtp = aiosmtplib.SMTP(
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    username=settings.SMTP_USER,
                    password=settings.SMTP_PASSWORD,
                    use_tls=getattr(settings, "SMTP_USE_TLS", False),
                    start_tls=getattr(settings, "SMTP_START_TLS", True),
                    timeout=getattr(settings, "SMTP_TIMEOUT", 60),
                )

                async with smtp:
                    await smtp.connect()
                    await smtp.ehlo_or_helo_if_needed()
                    if settings.SMTP_USER and settings.SMTP_PASSWORD:
                        await smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    await smtp.send_message(msg, sender=from_email, recipients=all_recipients)

                logger.info(
                    "EMAIL_SENT",
                    extra={
                        "to_count": len(to_addrs),
                        "subject": _truncate_str(subject_sanitized, 150),
                        "attempt": attempt,
                        "user_id": user_id,
                        "ip": _truncate_str(ip or "", 45),
                        "user_agent": _truncate_str(user_agent or "", 100),
                    },
                )

                # Audit push (safe)
                audit_entry = {
                    "user_id": user_id,
                    "action": "SEND_EMAIL",
                    "success": True,
                    "metadata": {
                        "masked_email": mask_email(user_email or "")[:MAX_METADATA_LENGTH],
                        "to_count": len(to_addrs),
                        "subject": _truncate_str(subject_sanitized, 150),
                        "ip": _truncate_str(ip or "", 45),
                        "user_agent": _truncate_str(user_agent or "", 100),
                        "attempt": attempt,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                }
                try:
                    redis_conn = await get_redis()
                    await redis_conn.rpush(settings.AUDIT_QUEUE_KEY, json.dumps(audit_entry, ensure_ascii=False))
                except Exception:
                    logger.exception("AUDIT_PUSH_FAILED – email already sent")

                break

            except (aiosmtplib.SMTPException, ConnectionError, OSError, asyncio.TimeoutError) as exc:
                last_exception = exc
                delay = min((2 ** attempt) * (1 + random.random() * 0.5), max_delay)
                logger.warning(
                    "EMAIL_ATTEMPT_FAILED",
                    extra={"attempt": attempt, "error": str(exc), "retry_delay_sec": delay},
                )
                if attempt == max_retries:
                    raise AppBaseException(503, {"message": "Failed to send email after retries", "error_code": "EMAIL_SERVICE_UNEXPECTED"})
                await asyncio.sleep(delay)

            except Exception as exc:
                last_exception = exc
                logger.exception("EMAIL_CRITICAL_ERROR", extra={"error": str(exc)})
                raise AppBaseException(500, {"message": "Unexpected email error", "error_code": "EMAIL_SERVICE_UNEXPECTED"})

    asyncio.run(_send_email())
