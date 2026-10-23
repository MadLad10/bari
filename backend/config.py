"""Application settings, loaded from environment variables and an optional .env file."""
import os
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
    # Serverless (Vercel): no connection pool, and no server-side prepared statements (they break behind
    # a transaction-mode pooler such as Neon's).
    db_serverless: bool = False
    # "worker" = background worker process; "inline" = run queued jobs at the end of each write request
    # (Vercel has no always-on worker).
    jobs_mode: str = "worker"
    # Assistant turns per client (user or IP) per hour; 0 = unlimited. Protects a public demo's LLM quota.
    ai_rate_limit_per_hour: int = 0
    # Scout (LangGraph). Checkpoints can use a direct (unpooled) URL; defaults to DATABASE_URL.
    checkpoint_database_url: str = ""
    scout_max_candidates: int = 5
    scout_manual_runs_per_day: int = 3
    cron_secret: str = ""

    # Seeded demo accounts. Set ADMIN_PASSWORD to a secret in production: the demo password is public.
    demo_password: str = "bari-demo-123"
    admin_password: str = ""
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8001",
        "http://localhost:4173",
    ]
    upload_dir: str = "uploads"
    private_upload_dir: str = "private_uploads"

    # Auth
    jwt_secret: str = "dev-only-insecure-secret-change-me-in-env"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    bcrypt_rounds: int = 12

    # LLM: "api" = OpenAI-compatible endpoint (Groq by default), "ollama" = local, "fake" = tests
    llm_provider: str = "api"
    llm_api_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_api_model: str = "openai/gpt-oss-120b"
    llm_timeout_s: float = 45
    llm_max_retries: int = 3
    llm_prices_json: str = ""

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_num_ctx: int = 16384
    ollama_timeout_s: float = 180

    # Retrieval
    embedding_provider: str = "ollama"     # ollama | gemini | fake
    gemini_api_key: str = ""
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_model: str = "bge-m3"
    reranker: str = "bge"                  # bge | fake | none
    reranker_model: str = "BAAI/bge-reranker-v2-m3-int8"
    reranker_cache_dir: str = "/home/app/.cache/fastembed"
    # Cross-encoder cost is ~0.3–0.5 s per pair on a shared laptop CPU, so only the top fused candidates are reranked.
    rerank_top: int = 10

    # Agent limits
    agent_max_tool_calls: int = 6
    agent_max_llm_steps: int = 5
    agent_tool_timeout_s: float = 10
    agent_turn_timeout_s: float = 150
    agent_injection_filter: bool = True
    pending_action_ttl_min: int = 30


def normalize_database_url(url: str) -> str:
    """Hosted Postgres (Neon, Vercel) hands out postgres:// URLs; SQLAlchemy needs the psycopg driver named."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


# Defaults that make the backend run on Vercel without extra configuration. Vercel sets VERCEL=1 in its
# runtime; any of these can still be overridden with an explicit environment variable.
VERCEL_DEFAULTS = {
    "db_serverless": True,       # one connection per invocation; Neon's pooler pools
    "jobs_mode": "inline",       # no always-on worker process
    "reranker": "none",          # the ONNX cross-encoder is too large for a function
    "upload_dir": "/tmp/uploads",  # the only writable path (ephemeral)
    "private_upload_dir": "/tmp/private_uploads",
}


def apply_platform_defaults(s: Settings, environ=os.environ) -> Settings:
    if environ.get("VERCEL"):
        for field, value in VERCEL_DEFAULTS.items():
            if field.upper() not in environ:
                setattr(s, field, value)
    return s


@lru_cache
def get_settings() -> Settings:
    s = apply_platform_defaults(Settings())
    s.database_url = normalize_database_url(s.database_url)
    return s


settings = get_settings()
