from datetime import datetime
from typing import Annotated
from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class ConversationCreate(BaseModel):
    title: str | None = None


class Conversation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    folder_id: PyObjectId
    user_id: PyObjectId
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    folder_id: PyObjectId
    user_id: PyObjectId
    title: str
    created_at: datetime
    updated_at: datetime
