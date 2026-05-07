from datetime import datetime
from enum import Enum
from typing import Annotated
from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Citation(BaseModel):
    chunk_id: str
    file_id: str | None = None
    file_name: str = ""
    snippet: str = ""
    score: float = 0.0


class RetrievalTrace(BaseModel):
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    rerank_scores: list[float] = Field(default_factory=list)
    latency_ms: int = 0
    model: str = ""


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    num_queries: int = Field(default=1, ge=1, le=4)


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    conversation_id: PyObjectId
    role: MessageRole
    content: str
    citations: list[Citation] = Field(default_factory=list)
    retrieval_trace: RetrievalTrace | None = None
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    conversation_id: PyObjectId
    role: MessageRole
    content: str
    citations: list[Citation] = Field(default_factory=list)
    retrieval_trace: RetrievalTrace | None = None
    created_at: datetime
