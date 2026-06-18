from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from app.db.base import Base

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token = Column(String(128), nullable=False, index=True)
    salt = Column(String(32), nullable=False)
    expires_at = Column(DateTime(timezone=True), index=True)
    used = Column(Boolean, default=False, index=True)

    __table_args__ = (
        Index("ix_reset_user_used_exp", "user_id", "used", "expires_at"),
    )
