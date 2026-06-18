import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse

from app.core.settings import settings
from app.core.exceptions.base import AppBaseException
from app.core.logging import logger
from app.core.redis_service import RedisService, RedisError
from app.core.security import hash_token
from app.db.session import SessionLocal
from app.models.security_token import SecurityToken
from app.models.email_outbox import EmailOutbox
from app.services.audit_service import AuditService
from app.utils.email_utils import mask_email
from app.utils.network import get_real_ip


redis = RedisService()


class VerificationEmailService:
    EMAIL_TOKEN_PURPOSE = settings.EMAIL_TOKEN_PURPOSE
    MAX_ACTIVE_TOKENS = 5
    MAX_EMAIL_BODY_BYTES = 30_000
    COOLDOWN_TTL = settings.COOLDOWN_MINUTES * 60
    TOKEN_TTL = settings.EMAIL_VERIFY_EXP_MIN * 60
    FINGERPRINT_SALT = settings.SECURITY_SALT

    async def _safe_decrement(self, key: str, ttl: int):
        try:
            value = await redis.increment(key, amount=-1)
            if value < 0:
                await redis.set_key(key, "0", expire=ttl)
        except Exception:
            logger.warning("REDIS_DECREMENT_FAILED", extra={"key": key})

    async def _increment_active_with_limit(self, key: str, max_count: int, ttl: int) -> int:
        """Atomic active token increment using Lua script"""
        script = """
        local count = redis.call('INCR', KEYS[1])
        if count > tonumber(ARGV[1]) then
            redis.call('DECR', KEYS[1])
            return -1
        end
        if count == 1 then
            redis.call('EXPIRE', KEYS[1], ARGV[2])
        end
        return count
        """
        result = await redis.eval(script, keys=[key], args=[max_count, ttl])
        if result == -1:
            raise AppBaseException(429, {"error_code": "TOO_MANY_ACTIVE_TOKENS"})
        return result

    async def _queue_audit_log(
        self,
        user_email: str,
        ip: Optional[str],
        user_agent: Optional[str],
        token_expires_at: datetime,
    ):
        db: Session = SessionLocal()
        try:
            await AuditService.log(
                db=db,
                user_id=None,
                action="SEND_VERIFY_EMAIL",
                success=True,
                metadata={
                    "masked_email": mask_email(user_email),
                    "token_expires_at": token_expires_at.isoformat(),
                    "ip": ip[:45] if ip else None,
                    "user_agent": (user_agent or "")[:180],
                },
                flush=True,
            )
        except Exception:
            logger.warning("AUDIT_LOG_FAILURE_AFTER_SUCCESS", extra={"email": user_email})
        finally:
            db.close()

    async def send_verification_email(
        self,
        db: Session,
        user,
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> Tuple[JSONResponse, BackgroundTasks]:

        user_id = user.id
        user_email = user.email

        # ================= FINGERPRINT SECURE =================
        ip = (get_real_ip(request) or "unknown")[:45]
        ua = (request.headers.get("user-agent", "unknown") or "")[:180]
        fingerprint_raw = f"{ip}:{ua}:{self.FINGERPRINT_SALT}"
        fingerprint = hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest()[:32]

        cooldown_key_user = f"verify:cooldown:user:{user_id}"
        cooldown_key_fp = f"verify:cooldown:fp:{fingerprint}"
        active_key = f"verify:active_tokens:{user_id}"

        # ================= COOLDOWN =================
        try:
            user_cooldown = await redis.set_key(cooldown_key_user, "1", expire=self.COOLDOWN_TTL, nx=True)
            fp_cooldown = await redis.set_key(cooldown_key_fp, "1", expire=self.COOLDOWN_TTL, nx=True)
            if not user_cooldown or not fp_cooldown:
                raise AppBaseException(
                    429,
                    {
                        "message": f"Please wait {settings.COOLDOWN_MINUTES} minutes before requesting a new email",
                        "error_code": "COOLDOWN_ACTIVE",
                    },
                )
        except RedisError:
            logger.error("REDIS_COOLDOWN_FAILED", exc_info=True)
            raise AppBaseException(503, {"error_code": "REDIS_UNAVAILABLE"})

        # ================= ACTIVE TOKEN LIMIT =================
        try:
            await self._increment_active_with_limit(active_key, self.MAX_ACTIVE_TOKENS, self.TOKEN_TTL)
        except RedisError:
            logger.error("REDIS_ACTIVE_TOKEN_FAILED", exc_info=True)
            raise AppBaseException(503, {"error_code": "REDIS_UNAVAILABLE"})

        # ================= INVALIDATE OLD TOKENS =================
        now = datetime.now(timezone.utc)
        try:
            old_tokens = (
                db.query(SecurityToken)
                .filter(
                    SecurityToken.user_id == user_id,
                    SecurityToken.purpose == self.EMAIL_TOKEN_PURPOSE,
                    SecurityToken.used == False,
                    SecurityToken.expires_at > now,
                )
                .all()
            )
            for t in old_tokens:
                t.used = True
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("OLD_TOKENS_INVALIDATION_FAILED", extra={"user_id": user_id})

        # ================= CREATE NEW TOKEN =================
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        token = SecurityToken(
            user_id=user_id,
            purpose=self.EMAIL_TOKEN_PURPOSE,
            token=token_hash,
            expires_at=now + timedelta(seconds=self.TOKEN_TTL),
            used=False,
            created_at=now,
        )
        db.add(token)

        # ================= EMAIL BODY =================
        verify_url = f"{settings.FRONTEND_BASE_URL}/verify-email?token={raw_token}"
        full_name = getattr(user, "full_name", getattr(user, "username", "User"))
        email_body = (
            f"{full_name},\n\n"
            f"برای تأیید ایمیل خود روی لینک زیر کلیک کنید:\n{verify_url}\n\n"
            f"این لینک تا {token.expires_at.strftime('%Y-%m-%d %H:%M')} معتبر است.\n"
            "اگر شما این درخواست را نداده‌اید، این ایمیل را نادیده بگیرید."
        )

        if len(email_body.encode("utf-8")) > self.MAX_EMAIL_BODY_BYTES:
            raise AppBaseException(500, {"error_code": "EMAIL_BODY_TOO_LARGE"})

        # ================= ADD EMAIL TO OUTBOX =================
        db.add(
            EmailOutbox(
                to=user_email,
                subject="تأیید آدرس ایمیل شما",
                body=email_body,
            )
        )

        # ================= COMMIT DB =================
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            await self._safe_decrement(active_key, self.TOKEN_TTL)
            logger.exception("VERIFY_EMAIL_DB_ERROR", extra={"user_id": user_id})
            raise AppBaseException(500, {"error_code": "DB_ERROR"})

        # ================= AUDIT LOG VIA BACKGROUND TASK =================
        background_tasks.add_task(
            self._queue_audit_log,
            user_email=user_email,
            ip=ip,
            user_agent=ua,
            token_expires_at=token.expires_at,
        )

        # ================= RETURN SAFE RESPONSE =================
        if settings.ENVIRONMENT == "development":
            return JSONResponse(
                status_code=200,
                content={"message": "Verification email queued", "status": "queued", "token": raw_token},
            ), background_tasks

        return JSONResponse(
            status_code=200,
            content={"message": "Verification email queued", "status": "queued"},
        ), background_tasks
