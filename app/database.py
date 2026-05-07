from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from app.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.MONGODB_URI)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    client = get_client()
    settings = get_settings()
    db_name = settings.MONGODB_URI.rsplit("/", 1)[-1].split("?")[0] or "ragdb"
    return client[db_name]


async def create_indexes() -> None:
    db = get_database()

    await db.files.create_indexes([
        IndexModel([("folder_id", ASCENDING), ("file_hash", ASCENDING)], unique=True),
        IndexModel([("folder_id", ASCENDING)]),
        IndexModel([("user_id", ASCENDING)]),
    ])

    await db.chunks.create_indexes([
        IndexModel([("folder_id", ASCENDING)]),
        IndexModel([("file_id", ASCENDING)]),
        IndexModel([("metadata.parent_id", ASCENDING)]),
    ])

    await db.conversations.create_indexes([
        IndexModel([("folder_id", ASCENDING), ("updated_at", DESCENDING)]),
        IndexModel([("user_id", ASCENDING)]),
    ])

    await db.messages.create_indexes([
        IndexModel([("conversation_id", ASCENDING), ("created_at", ASCENDING)]),
    ])

    await db.users.create_indexes([
        IndexModel([("email", ASCENDING)], unique=True),
    ])


async def close_database() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
