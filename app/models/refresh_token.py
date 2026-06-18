from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from datetime import datetime
from app.db.base import Base

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"


    token = Column(String, unique=True, index=True)
    revoked = Column(Boolean, default=False)
    expires_at = Column(DateTime)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
