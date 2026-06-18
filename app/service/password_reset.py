import secrets
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.password_reset import PasswordResetToken


class PasswordResetService:
    TOKEN_EXPIRE_MINUTES = 30
    MAX_ACTIVE_TOKENS = 5
    TOKEN_BYTES = 48  # future-proof

    @staticmethod
    def _hash(raw: str, salt: bytes) -> str:
        return hashlib.sha256(salt + raw.encode()).hexdigest()

    @classmethod
    def create_token(cls, db: Session, user_id: int) -> str:
        raw = secrets.token_urlsafe(cls.TOKEN_BYTES)
        salt = secrets.token_bytes(16)
        now = datetime.now(timezone.utc)

        with db.begin():
            db.query(PasswordResetToken).filter(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used.is_(False),
            ).update({"used": True}, synchronize_session=False)

            tokens = (
                db.query(PasswordResetToken)
                .filter(PasswordResetToken.user_id == user_id)
                .order_by(PasswordResetToken.id.asc())
                .all()
            )

            for t in tokens[:-cls.MAX_ACTIVE_TOKENS]:
                db.delete(t)

            db.add(
                PasswordResetToken(
                    user_id=user_id,
                    token=cls._hash(raw, salt),
                    salt=salt.hex(),
                    expires_at=now + timedelta(minutes=cls.TOKEN_EXPIRE_MINUTES),
                    used=False,
                )
            )

        return raw

    @classmethod
    def verify_and_consume(cls, db: Session, raw_token: str) -> int:
        now = datetime.now(timezone.utc)

        tokens = (
            db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.used.is_(False),
                PasswordResetToken.expires_at > now,
            )
            .with_for_update()
            .all()
        )

        for t in tokens:
            calc = cls._hash(raw_token, bytes.fromhex(t.salt))
            if hmac.compare_digest(calc, t.token):
                t.used = True
                return t.user_id

        raise ValueError("INVALID_OR_EXPIRED_TOKEN")
