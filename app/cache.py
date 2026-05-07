import hashlib
import json
import pickle
from typing import Any
import redis.asyncio as aioredis
from app.config import get_settings

_redis: aioredis.Redis | None = None

EMBEDDING_TTL = 86400 * 30   # 30 days
QUERY_RESULT_TTL = 600        # 10 minutes
FOLDER_META_TTL = 3600        # 1 hour


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def _embedding_key(model: str, enriched_text: str) -> str:
    digest = hashlib.sha256(f"{model}{enriched_text}".encode()).hexdigest()
    return f"emb:{digest}"


def _query_key(folder_id: str, query: str, top_k: int, rerank_model: str) -> str:
    normalized = query.strip().lower()
    digest = hashlib.sha256(f"{folder_id}{normalized}{top_k}{rerank_model}".encode()).hexdigest()
    return f"qry:{digest}"


def _folder_key(folder_id: str) -> str:
    return f"folder:{folder_id}"


async def get_embedding(model: str, enriched_text: str) -> list[float] | None:
    r = get_redis()
    data = await r.get(_embedding_key(model, enriched_text))
    if data:
        return pickle.loads(data)
    return None


async def set_embedding(model: str, enriched_text: str, vector: list[float]) -> None:
    r = get_redis()
    await r.setex(_embedding_key(model, enriched_text), EMBEDDING_TTL, pickle.dumps(vector))


async def get_query_result(folder_id: str, query: str, top_k: int, rerank_model: str) -> Any | None:
    r = get_redis()
    data = await r.get(_query_key(folder_id, query, top_k, rerank_model))
    if data:
        return json.loads(data)
    return None


async def set_query_result(folder_id: str, query: str, top_k: int, rerank_model: str, result: Any) -> None:
    r = get_redis()
    await r.setex(_query_key(folder_id, query, top_k, rerank_model), QUERY_RESULT_TTL, json.dumps(result))


async def get_folder_meta(folder_id: str) -> dict | None:
    r = get_redis()
    data = await r.get(_folder_key(folder_id))
    if data:
        return json.loads(data)
    return None


async def set_folder_meta(folder_id: str, folder_doc: dict) -> None:
    r = get_redis()
    await r.setex(_folder_key(folder_id), FOLDER_META_TTL, json.dumps(folder_doc, default=str))


async def invalidate_folder_meta(folder_id: str) -> None:
    r = get_redis()
    await r.delete(_folder_key(folder_id))


# ---------------------------------------------------------------------------
# BM25 node cache — stores serialised leaf node dicts per folder.
# Invalidated whenever a file is ingested or deleted so the next query
# rebuilds the index from the docstore and re-caches it.
# ---------------------------------------------------------------------------

BM25_TTL = 86400  # 24 hours


def _bm25_key(folder_id: str) -> str:
    return f"bm25:{folder_id}"


async def get_bm25_nodes(folder_id: str) -> list[dict] | None:
    r = get_redis()
    data = await r.get(_bm25_key(folder_id))
    if data:
        return json.loads(data)
    return None


async def set_bm25_nodes(folder_id: str, nodes: list[dict]) -> None:
    r = get_redis()
    await r.setex(_bm25_key(folder_id), BM25_TTL, json.dumps(nodes))


async def invalidate_bm25_cache(folder_id: str) -> None:
    r = get_redis()
    await r.delete(_bm25_key(folder_id))
