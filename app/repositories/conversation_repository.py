from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class ConversationRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db.conversations

    async def list_by_folder(self, folder_id: str) -> list[dict]:
        return await self._col.find(
            {"folder_id": ObjectId(folder_id)},
            sort=[("updated_at", -1)],
        ).to_list(None)

    async def get_by_id(self, conversation_id: str) -> dict | None:
        return await self._col.find_one({"_id": ObjectId(conversation_id)})

    async def get_by_id_and_user(self, conversation_id: str, user_id: str) -> dict | None:
        return await self._col.find_one({
            "_id": ObjectId(conversation_id),
            "user_id": ObjectId(user_id),
        })

    async def list_ids_by_folder(self, folder_id: str) -> list[ObjectId]:
        return await self._col.distinct("_id", {"folder_id": ObjectId(folder_id)})

    async def create(self, folder_id: str, user_id: str, title: str) -> dict:
        now = datetime.now(timezone.utc)
        doc = {
            "_id": ObjectId(),
            "folder_id": ObjectId(folder_id),
            "user_id": ObjectId(user_id),
            "title": title,
            "created_at": now,
            "updated_at": now,
        }
        await self._col.insert_one(doc)
        return doc

    async def update_title(self, conversation_id: str, title: str) -> None:
        await self._col.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"title": title, "updated_at": datetime.now(timezone.utc)}},
        )

    async def touch(self, conversation_id: str) -> None:
        """Update updated_at to now."""
        await self._col.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"updated_at": datetime.now(timezone.utc)}},
        )

    async def delete(self, conversation_id: str) -> None:
        await self._col.delete_one({"_id": ObjectId(conversation_id)})

    async def delete_by_folder(self, folder_id: str) -> None:
        await self._col.delete_many({"folder_id": ObjectId(folder_id)})
