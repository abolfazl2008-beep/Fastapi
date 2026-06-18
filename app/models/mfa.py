from sqlalchemy import Column, String, Boolean, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from app.db.base import Base

class MFASecret(Base):
    __tablename__ = "mfa_secrets"

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    secret = Column(String, nullable=False)
    enabled = Column(Boolean, default=False)
    failed_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
