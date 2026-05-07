from datetime import datetime
from typing import Annotated
from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class FolderSettings(BaseModel):
    chunk_size: int = 512
    chunk_overlap: int = 50
    embedding_model: str = "text-embedding-3-small"


class FolderStats(BaseModel):
    file_count: int = 0
    chunk_count: int = 0
    total_tokens: int = 0


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    settings: FolderSettings = Field(default_factory=FolderSettings)


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    settings: FolderSettings | None = None


class Folder(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    user_id: PyObjectId
    name: str
    description: str | None
    pinecone_namespace: str
    stats: FolderStats
    settings: FolderSettings
    created_at: datetime
    updated_at: datetime


class FolderOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    user_id: PyObjectId
    name: str
    description: str | None
    pinecone_namespace: str
    stats: FolderStats
    settings: FolderSettings
    created_at: datetime
    updated_at: datetime
