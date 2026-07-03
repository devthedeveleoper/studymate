from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    # database (Aiven PostgreSQL)
    DATABASE_URL: str

    # caching (Aiven Valkey/Redis)
    VALKEY_URL: str = ""

    # auth
    JWT_SECRET: str
    JWT_LIFETIME_SECONDS: int = 3600  # 1 hour

    # ai provider
    AI_PROVIDER: Literal["ollama", "groq"] = "ollama"

    # ollama (local dev)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "qwen3:4b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # Groq & HuggingFace Configuration
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    HUGGINGFACE_API_KEY: str = ""

    # chunking and embedding config
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    EMBEDDING_DIM: int = 768

    # file upload
    MAX_UPLOAD_MB: int = 20

    model_config = {
        "env_file": (".env", "../.env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
