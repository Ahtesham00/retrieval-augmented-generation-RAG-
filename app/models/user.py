from datetime import datetime
from typing import Annotated
from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field, ConfigDict, BeforeValidator


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class User(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    email: EmailStr
    hashed_password: str
    created_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
