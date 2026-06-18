from sqlalchemy import Column, Integer, String
from db.base import Base

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
