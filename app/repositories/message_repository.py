from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class MessageRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db.messages

    async def list_by_conversation(
        self,
        conversation_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> list[dict]:
        skip = (page - 1) * page_size
        return await self._col.find(
            {"conversation_id": ObjectId(conversation_id)},
            sort=[("created_at", 1)],
            skip=skip,
            limit=page_size,
        ).to_list(None)

    async def get_history(self, conversation_id: str, last_n: int = 10) -> list[dict]:
        """Returns the last N messages for context building (role + content only)."""
        docs = await self._col.find(
            {"conversation_id": ObjectId(conversation_id)},
            {"role": 1, "content": 1},
            sort=[("created_at", 1)],
        ).to_list(None)
        return docs[-last_n:] if len(docs) > last_n else docs

    async def create(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: list[dict] | None = None,
        retrieval_trace: dict | None = None,
    ) -> dict:
        doc: dict[str, Any] = {
            "_id": ObjectId(),
            "conversation_id": ObjectId(conversation_id),
            "role": role,
            "content": content,
            "citations": citations or [],
            "retrieval_trace": retrieval_trace,
            "created_at": datetime.now(timezone.utc),
        }
        await self._col.insert_one(doc)
        return doc

    async def delete_by_conversation(self, conversation_id: str) -> None:
        await self._col.delete_many({"conversation_id": ObjectId(conversation_id)})

    async def delete_by_conversation_ids(self, conversation_ids: list[ObjectId]) -> None:
        if conversation_ids:
            await self._col.delete_many({"conversation_id": {"$in": conversation_ids}})
