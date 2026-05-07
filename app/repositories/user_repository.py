from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user import User, UserOut


class UserRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db.users

    async def get_by_email(self, email: str) -> dict | None:
        return await self._col.find_one({"email": email})

    async def get_by_id(self, user_id: str) -> dict | None:
        return await self._col.find_one({"_id": ObjectId(user_id)})

    async def email_exists(self, email: str) -> bool:
        return await self._col.find_one({"email": email}, {"_id": 1}) is not None

    async def create(self, email: str, hashed_password: str) -> dict:
        doc = {
            "_id": ObjectId(),
            "email": email,
            "hashed_password": hashed_password,
            "created_at": datetime.now(timezone.utc),
        }
        await self._col.insert_one(doc)
        return doc
