import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cache import close_redis
from app.database import close_database, create_indexes
from app.logging_config import setup_logging
from app.pinecone_client import ensure_index_exists
from app.routers import auth, chat, conversations, files, folders, health

# setup_logging() must be called before any other import that uses logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting up RAG API...")
    logger.info("Creating MongoDB indexes...")
    await create_indexes()
    logger.info("MongoDB indexes ready.")
    try:
        logger.info("Ensuring Pinecone index exists...")
        ensure_index_exists()
        logger.info("Pinecone index ready.")
    except Exception as exc:
        logger.warning("Pinecone index check failed (may already exist): %s", exc)
    logger.info("RAG API startup complete.")
    yield
    logger.info("Shutting down RAG API...")
    await close_database()
    await close_redis()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="RAG API",
    description="Document-based chat with retrieval-augmented generation.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(folders.router)
app.include_router(files.router)
app.include_router(conversations.router)
app.include_router(chat.router)
