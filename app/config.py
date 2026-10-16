"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _railway_public_url() -> str | None:
    """Railway injects RAILWAY_PUBLIC_DOMAIN (and sometimes RAILWAY_STATIC_URL)."""
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("RAILWAY_STATIC_URL")
    if not domain:
        return None
    if domain.startswith(("http://", "https://")):
        return domain.rstrip("/")
    return f"https://{domain}"


class Settings(BaseSettings):
    """Strongly-typed environment configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: str = Field(..., description="Bot token issued by @BotFather")
    telegram_bot_username: str = Field(
        "FinFaccoBot", description="Public bot @username (without @)"
    )
    github_repo_url: str = Field(
        "https://github.com/DiovaniFacco/finza-telegram",
        description="Public repository URL shown on the landing page",
    )
    openrouter_api_key: str = Field("", description="OpenRouter API key (optional)")
    database_url: str = Field(..., description="Postgres connection string")
    app_url: str = Field("http://localhost:8000", description="Public base URL of the app")
    secret_key: str = Field(..., description="Secret used for JWT and session signing")
    webhook_secret: str = Field("expense-bot", description="Secret path segment for /webhook")
    app_tz: str = Field("America/Sao_Paulo", description="Timezone for daily reports")
    log_level: str = Field("INFO", description="Logging level")

    @field_validator("database_url")
    @classmethod
    def _ensure_async_driver(cls, v: str) -> str:
        """Convert sync postgres URLs to async SQLAlchemy + asyncpg form."""
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        return v

    @model_validator(mode="after")
    def _resolve_public_url_on_railway(self) -> "Settings":
        """On Railway, use the platform public URL — unless the user set a
        custom domain via APP_URL (e.g. https://financas.sfacco.com.br)."""
        if self.app_url and "localhost" not in self.app_url and "127.0.0.1" not in self.app_url:
            self.app_url = self.app_url.rstrip("/")
            return self
        railway_url = _railway_public_url()
        if railway_url and os.getenv("RAILWAY_ENVIRONMENT"):
            object.__setattr__(self, "app_url", railway_url)
        return self

    @property
    def sync_database_url(self) -> str:
        """Synchronous URL for Alembic migrations (psycopg driver)."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            url = "postgresql+psycopg://" + url[len("postgresql+asyncpg://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @property
    def webhook_path(self) -> str:
        return f"/webhook/{self.webhook_secret}"

    @property
    def bot_url(self) -> str:
        """Deep link that opens the bot in Telegram."""
        return f"https://t.me/{self.telegram_bot_username.lstrip('@')}"

    @property
    def webhook_url(self) -> str:
        return self.app_url.rstrip("/") + self.webhook_path

    @property
    def is_supabase_or_ssl(self) -> bool:
        u = self.database_url.lower()
        return (
            "supabase" in u
            or "pooler.supabase.com" in u
            or "sslmode=require" in u
            or "ssl=true" in u
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
