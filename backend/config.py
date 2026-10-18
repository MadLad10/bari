"""Application settings, loaded from environment variables and an optional .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ROOT / ".env", Path(__file__).resolve().parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"
    database_url: str = "sqlite:///./bari.db"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8001",
    ]
    upload_dir: str = "uploads"

    # Auth
    jwt_secret: str = "dev-only-insecure-secret-change-me-in-env"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    bcrypt_rounds: int = 12

    # LLM: "api" = OpenAI-compatible endpoint (Groq by default), "ollama" = local, "fake" = tests
    llm_provider: str = "api"
    llm_api_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_api_model: str = "llama-3.3-70b-versatile"
    llm_timeout_s: float = 45
    llm_max_retries: int = 3
    llm_prices_json: str = ""

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_num_ctx: int = 16384
    ollama_timeout_s: float = 180

    # Retrieval
    embedding_provider: str = "ollama"     # ollama | fake
    embedding_model: str = "bge-m3"
    reranker: str = "bge"                  # bge | fake | none
    reranker_model: str = "BAAI/bge-reranker-v2-m3-int8"
    reranker_cache_dir: str = "/home/app/.cache/fastembed"
    # Cross-encoder cost is ~0.3–0.5 s per pair on a shared laptop CPU, so only the top fused candidates are reranked.
    rerank_top: int = 10

    # Legacy prompt-stuffing assistant (replaced by the agent in M6).
    openai_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
