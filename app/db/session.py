"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.db.ssl_config import asyncpg_ssl_context, needs_ssl


def _connect_args() -> dict:
    """Hosted Postgres (Supabase, Railway) needs SSL; poolers need no statement cache."""
    args: dict = {}
    url = settings.database_url.lower()

    if needs_ssl(url):
        args["ssl"] = asyncpg_ssl_context()

    # Supabase transaction pooler + asyncpg: disable prepared statement cache.
    if "pooler" in url or "pgbouncer" in url or "6543" in url:
        args["statement_cache_size"] = 0

    return args


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    future=True,
    connect_args=_connect_args(),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a session and rolls back on errors."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database() -> None:
    """Verify DB connectivity at startup; raises on failure."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
