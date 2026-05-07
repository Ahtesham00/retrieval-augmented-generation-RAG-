from pinecone import Pinecone, ServerlessSpec
from app.config import get_settings

_pinecone: Pinecone | None = None


def get_pinecone() -> Pinecone:
    global _pinecone
    if _pinecone is None:
        settings = get_settings()
        _pinecone = Pinecone(api_key=settings.PINECONE_API_KEY)
    return _pinecone


def get_index():
    settings = get_settings()
    pc = get_pinecone()
    return pc.Index(settings.PINECONE_INDEX)


def ensure_index_exists() -> None:
    settings = get_settings()
    pc = get_pinecone()
    existing = [idx.name for idx in pc.list_indexes()]
    if settings.PINECONE_INDEX not in existing:
        pc.create_index(
            name=settings.PINECONE_INDEX,
            dimension=settings.EMBEDDING_DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(cloud=settings.PINECONE_CLOUD, region=settings.PINECONE_REGION),
        )


def make_namespace(user_id: str, folder_id: str) -> str:
    return f"user_{user_id}__folder_{folder_id}"
