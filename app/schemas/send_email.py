
from pydantic import BaseModel, EmailStr, Field

class EmailRequest(BaseModel):
    to: EmailStr = Field(...,description="Email address of the recipient",example="user@example.com")
    subject: str = Field(...,min_length=3,max_length=200,description="Email subject line",example="Important Update")
    body: str = Field( ...,min_length=5,description="Plain text body of the email",example="Hello, this is a test message.")
    is_html: bool = Field(default=False,description="If true, the body is treated as HTML")

    model_config = {
        "json_schema_extra": {
            "example": {
                "to": "user@example.com",
                "subject": "Welcome to our platform",
                "body": "Thank you for registering!",
                "is_html": False
            }
        }
    }
    