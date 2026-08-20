from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at <api-root>/app/config.py whether we are in the monorepo
# (…/AgentLens/apps/api/app/…) or a Docker image (…/app/app/…). Never index past
# the filesystem root — that blew up on Render with IndexError: 3.
_API_ROOT = Path(__file__).resolve().parents[1]


def _env_files() -> tuple[Path, ...]:
    candidates: list[Path] = []
    # Local monorepo: apps/api/../../.env
    if len(Path(__file__).resolve().parents) > 3:
        candidates.append(Path(__file__).resolve().parents[3] / ".env")
    candidates.append(_API_ROOT / ".env")
    return tuple(candidates)


def normalize_database_url(raw: str) -> str:
    """Make a Neon / Render DATABASE_URL safe for SQLAlchemy + asyncpg."""

    url = raw.strip().strip('"').strip("'")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    if "+asyncpg" not in url:
        return url

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query = {k: v for k, v in query.items() if k and v != ""}
    if "sslmode" in query:
        mode = query.pop("sslmode")
        if mode and mode.lower() != "disable":
            query.setdefault("ssl", "require")
    if "ssl" in query and query["ssl"].lower() in {"true", "1", "yes"}:
        query["ssl"] = "require"

    return urlunparse(parsed._replace(query=urlencode(query)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
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

    @field_validator("database_url", mode="before")
    @classmethod
    def _clean_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_database_url(value)
        return value

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
