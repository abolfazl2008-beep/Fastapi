
from typing import Annotated, Optional
from pydantic import BaseModel, StringConstraints, ConfigDict, Field

class PostCreate(BaseModel):
    title: Annotated[str, StringConstraints(min_length=5, max_length=150)] = Field(..., description="Post title")
    content: str | None = Field(default=None, description="Post content (markdown supported)")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "My First Post",
                "content": "This is the body of my post..."
            }
        }
    )


class PostUpdate(BaseModel):
    title: Annotated[str | None, StringConstraints(min_length=5, max_length=150)] = Field(
        default=None, description="New title (optional)"
    )
    content: str | None = Field(default=None, description="New content (optional)")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "title": "Updated Title"
            }
        }
    )


class PostOut(BaseModel):
    id: int
    user_id: int
    title: str
    content: str | None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "user_id": 42,
                "title": "My First Post",
                "content": "This is the body..."
            }
        }
    )
