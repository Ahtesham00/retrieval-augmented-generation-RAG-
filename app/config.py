from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI
    OPENAI_API_KEY: str

    # Pinecone
    PINECONE_API_KEY: str
    PINECONE_INDEX: str = "rag-prod"
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"

    # MongoDB
    MONGODB_URI: str = "mongodb://localhost:27017/ragdb"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    JWT_SECRET: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Models
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    CHAT_MODEL: str = "gpt-4o-mini"
    EMBEDDING_DIMENSIONS: int = 1536

    # Ingestion limits
    MAX_FILE_SIZE_MB: int = 50
    UPLOAD_DIR: str = "uploads"
    MAX_FILES_PER_FOLDER: int = 100
    MAX_FOLDERS_PER_USER: int = 20

    @field_validator("EMBEDDING_DIMENSIONS")
    @classmethod
    def validate_dimensions(cls, v: int) -> int:
        allowed = {1536, 3072}
        if v not in allowed:
            raise ValueError(f"EMBEDDING_DIMENSIONS must be one of {allowed}")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
