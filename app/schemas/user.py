from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class UserBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=50, description="نام کامل کاربر")
    age: int = Field(..., ge=5, le=120, description="سن کابر(5تا60سال)")
    email: EmailStr = Field(..., description="ایمیل معتبر کاربر")


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128, description="پسورد حداقل ۸ کاراکتر")
    role: Optional[UserRole] = Field(
        default=UserRole.USER,
        description="نقش کاربر (user یا admin)، پیش‌فرض user"
    )

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    age: Optional[int] = Field(None, ge=5, le=120)
    role: Optional[UserRole] = Field(None, description="تغییر نقش کاربر")

class UserOut(UserBase):
    id: int
    role: UserRole

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "abolfazl",
                "age": 17,
                "email": "abolfazl@example.com",
                "role": "user"
            }
        }

