
import re
from pydantic import BaseModel, EmailStr, validator

class ResetRequest(BaseModel):
    email: EmailStr

class ResetConfirm(BaseModel):
    token: str
    new_password: str

    @validator("new_password")
    def validate_password(cls, v):
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must include at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must include at least one number")
        if not re.search(r"[!@#$%^&*()_\-+=]", v):
            raise ValueError("Password must include at least one special character")
        return v
