from pydantic import BaseModel, Field

class Get(BaseModel):
    name: str = Field(..., min_length=20, max_length=30)
    family: str = Field(..., min_length=20, max_length=30)

class Post(BaseModel):
    name: str = Field(..., min_length=20, max_length=30)
    family: str = Field(..., min_length=20, max_length=30)

class Put(BaseModel):
    name: str = Field(..., min_length=20, max_length=30)
    family: str = Field(..., min_length=20, max_length=30)

class Delete(BaseModel):
    name: str = Field(..., min_length=20, max_length=30)
    family: str = Field(..., min_length=20, max_length=30)

