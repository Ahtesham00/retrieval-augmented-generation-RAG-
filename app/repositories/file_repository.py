from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.file import FileStatus


class FileRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db.files

    async def list_by_folder(self, folder_id: str) -> list[dict]:
        return await self._col.find({"folder_id": ObjectId(folder_id)}).to_list(None)

    async def get_by_id(self, file_id: str) -> dict | None:
        return await self._col.find_one({"_id": ObjectId(file_id)})

    async def get_by_id_and_user(self, file_id: str, user_id: str) -> dict | None:
        return await self._col.find_one({
            "_id": ObjectId(file_id),
            "user_id": ObjectId(user_id),
        })

    async def get_by_hash(self, folder_id: str, file_hash: str, status: FileStatus | None = None) -> dict | None:
        query: dict[str, Any] = {"folder_id": ObjectId(folder_id), "file_hash": file_hash}
        if status:
            query["status"] = status.value
        return await self._col.find_one(query)

    async def get_by_name(self, folder_id: str, file_name: str) -> dict | None:
        return await self._col.find_one({"folder_id": ObjectId(folder_id), "file_name": file_name})

    async def count_by_folder(self, folder_id: str) -> int:
        return await self._col.count_documents({"folder_id": ObjectId(folder_id)})

    async def create(
        self,
        folder_id: str,
        user_id: str,
        file_name: str,
        file_extension: str,
        content_type: str,
        storage_path: str,
        file_hash: str,
        size_bytes: int,
    ) -> dict:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "_id": ObjectId(),
            "folder_id": ObjectId(folder_id),
            "user_id": ObjectId(user_id),
            "file_name": file_name,
            "file_extension": file_extension,
            "content_type": content_type,
            "storage_path": storage_path,
            "file_hash": file_hash,
            "size_bytes": size_bytes,
            "status": FileStatus.PENDING.value,
            "error": None,
            "parsing_strategy": "",
            "chunk_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await self._col.insert_one(doc)
        return doc

    async def update_status(
        self,
        file_id: str,
        status: FileStatus,
        error: str | None = None,
        chunk_count: int | None = None,
        parsing_strategy: str | None = None,
    ) -> None:
        fields: dict[str, Any] = {
            "status": status.value,
            "updated_at": datetime.now(timezone.utc),
        }
        if error is not None:
            fields["error"] = error
        if chunk_count is not None:
            fields["chunk_count"] = chunk_count
        if parsing_strategy is not None:
            fields["parsing_strategy"] = parsing_strategy
        await self._col.update_one({"_id": ObjectId(file_id)}, {"$set": fields})

    async def delete(self, file_id: str) -> None:
        await self._col.delete_one({"_id": ObjectId(file_id)})

    async def delete_by_folder(self, folder_id: str) -> None:
        await self._col.delete_many({"folder_id": ObjectId(folder_id)})
