from datetime import datetime
from typing import Annotated
from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class ChunkMetadata(BaseModel):
    file_name: str
    parser: str
    content_type: str
    section_path: list[str] = Field(default_factory=list)
    chunk_index: int
    parent_id: PyObjectId | None = None
    is_leaf: bool = True
    generated_questions: list[str] = Field(default_factory=list)
    summary: str | None = None


class Chunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    file_id: PyObjectId
    folder_id: PyObjectId
    user_id: PyObjectId
    text: str
    enriched_text: str
    metadata: ChunkMetadata
    created_at: datetime


class ChunkOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    file_id: PyObjectId
    folder_id: PyObjectId
    text: str
    metadata: ChunkMetadata
    created_at: datetime
