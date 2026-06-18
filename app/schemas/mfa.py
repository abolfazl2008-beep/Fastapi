
from pydantic import BaseModel, Field

class VerifyMFARequest(BaseModel):
    code: str = Field(...,min_length=6,max_length=6,pattern=r"^\d{6}$",description="6-digit MFA code",example="123456")

class VerifyMFAResponse(BaseModel):
    success: bool = True
