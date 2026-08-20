from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _API_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AgentLens API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://agentlens:agentlens@localhost:5432/agentlens"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    password_reset_token_expire_minutes: int = 60

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    api_prefix: str = "/api/v1"

    openai_api_key: str | None = None
    judge_model: str = "gpt-4o-mini"
    judge_base_url: str = "https://api.openai.com/v1"
    judge_timeout_seconds: float = 30.0
    max_evaluation_items: int = 2000

    rate_limit_enabled: bool = True
    rate_limit_requests: int = 1200
    rate_limit_window_seconds: int = 60
    max_request_bytes: int = 5 * 1024 * 1024

    stream_poll_seconds: float = 2.0
    stream_max_seconds: float = 900.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def uses_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def uses_memory_redis(self) -> bool:
        value = (self.redis_url or "").strip().lower()
        return value in {"", "memory://", "memory", "disabled", "none"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
