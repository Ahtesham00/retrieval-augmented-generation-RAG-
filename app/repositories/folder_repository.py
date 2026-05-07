from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.folder import FolderSettings, FolderStats


class FolderRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db.folders

    async def list_by_user(self, user_id: str) -> list[dict]:
        return await self._col.find({"user_id": ObjectId(user_id)}).to_list(None)

    async def get_by_id(self, folder_id: str) -> dict | None:
        return await self._col.find_one({"_id": ObjectId(folder_id)})

    async def get_by_id_and_user(self, folder_id: str, user_id: str) -> dict | None:
        return await self._col.find_one({
            "_id": ObjectId(folder_id),
            "user_id": ObjectId(user_id),
        })

    async def count_by_user(self, user_id: str) -> int:
        return await self._col.count_documents({"user_id": ObjectId(user_id)})

    async def create(
        self,
        user_id: str,
        name: str,
        description: str | None,
        pinecone_namespace: str,
        settings: FolderSettings,
        folder_id: ObjectId | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "_id": folder_id or ObjectId(),
            "user_id": ObjectId(user_id),
            "name": name,
            "description": description,
            "pinecone_namespace": pinecone_namespace,
            "stats": FolderStats().model_dump(),
            "settings": settings.model_dump(),
            "created_at": now,
            "updated_at": now,
        }
        await self._col.insert_one(doc)
        return doc

    async def update(self, folder_id: str, fields: dict[str, Any]) -> dict | None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._col.update_one({"_id": ObjectId(folder_id)}, {"$set": fields})
        return await self.get_by_id(folder_id)

    async def increment_stats(self, folder_id: str, file_delta: int = 0, chunk_delta: int = 0) -> None:
        inc: dict[str, int] = {}
        if file_delta:
            inc["stats.file_count"] = file_delta
        if chunk_delta:
            inc["stats.chunk_count"] = chunk_delta
        if inc:
            await self._col.update_one({"_id": ObjectId(folder_id)}, {"$inc": inc})

    async def delete(self, folder_id: str) -> None:
        await self._col.delete_one({"_id": ObjectId(folder_id)})
