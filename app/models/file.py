from datetime import datetime
from enum import Enum
from typing import Annotated
from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class FileStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"


class File(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    folder_id: PyObjectId
    user_id: PyObjectId
    file_name: str
    file_extension: str
    content_type: str
    storage_path: str
    file_hash: str
    size_bytes: int
    status: FileStatus
    error: str | None
    parsing_strategy: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class FileOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    folder_id: PyObjectId
    user_id: PyObjectId
    file_name: str
    file_extension: str
    content_type: str
    storage_path: str
    file_hash: str
    size_bytes: int
    status: FileStatus
    error: str | None
    parsing_strategy: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime
