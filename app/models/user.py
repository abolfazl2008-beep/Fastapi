from sqlalchemy import Column, Integer, String, Enum
from app.db.base import Base
from app.utils.enums import RoleEnum

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), nullable=False)
    is_email_verified = Column(Boolean, default=False)
    mfa_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    email = Column(String, unique=True, nullable=False, index=True)



