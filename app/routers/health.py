import logging
from fastapi import APIRouter
from app.cache import get_redis
from app.config import get_settings
from app.database import get_database
from app.pinecone_client import get_pinecone

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/health/deep")
async def deep_health() -> dict:
    results: dict = {}

    # MongoDB
    try:
        db = get_database()
        await db.command("ping")
        results["mongodb"] = "ok"
    except Exception as exc:
        logger.warning("MongoDB health check failed: %s", exc)
        results["mongodb"] = f"error: {exc}"

    # Redis
    try:
        r = get_redis()
        await r.ping()
        results["redis"] = "ok"
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        results["redis"] = f"error: {exc}"

    # Pinecone
    try:
        pc = get_pinecone()
        pc.list_indexes()
        results["pinecone"] = "ok"
    except Exception as exc:
        logger.warning("Pinecone health check failed: %s", exc)
        results["pinecone"] = f"error: {exc}"

    # OpenAI
    try:
        from openai import AsyncOpenAI
        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        await client.models.list()
        results["openai"] = "ok"
    except Exception as exc:
        logger.warning("OpenAI health check failed: %s", exc)
        results["openai"] = f"error: {exc}"

    overall = "ok" if all(v == "ok" for v in results.values()) else "degraded"
    return {"status": overall, "checks": results}
