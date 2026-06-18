from pydantic import BaseModel, EmailStr, Field, field_validator

class LoginRequest(BaseModel):
    username: EmailStr= Field(...,description="Email address or username",example="user@example.com")
    password: str = Field(...,min_length=8,description="User password",json_schema_extra={"format": "password"})

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    model_config = {
        "json_schema_extra": {
            "example": {
                "username": "user@example.com",
                "password": "StrongPass123!"
            }
        }
    }
