from sqlalchemy import Column, String, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.db.base_class import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True)
    fingerprint = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), index=True, nullable=False)
    action = Column(String(120), index=True, nullable=False)
    success = Column(Boolean, nullable=False)
    user_id = Column(String(128), index=True)
    ip = Column(String(64))
    user_agent = Column(String(512))
    request_id = Column(String(120), index=True)
    metadata = Column(JSONB, default=dict)

    __table_args__ = (
        Index("ix_audit_created_action", "created_at", "action"),
    )
