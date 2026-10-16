"""SSL settings for hosted Postgres (Supabase, Railway).

Managed providers often use certificates that fail Python's default CA verification.
We still encrypt the connection but skip strict cert chain verification unless
DATABASE_SSL_VERIFY=true is set.
"""

from __future__ import annotations

import os
import ssl


def needs_ssl(url: str) -> bool:
    u = url.lower()
    return (
        "supabase" in u
        or "pooler.supabase.com" in u
        or "railway" in u
        or "sslmode=require" in u
        or bool(os.getenv("RAILWAY_ENVIRONMENT"))
    )


def strict_verify_enabled() -> bool:
    return os.getenv("DATABASE_SSL_VERIFY", "").lower() in ("1", "true", "yes")


def asyncpg_ssl_context() -> ssl.SSLContext | bool:
    """Return an SSL context suitable for asyncpg + Supabase/Railway."""
    if strict_verify_enabled():
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def psycopg_connect_args(url: str) -> dict:
    """connect_args for psycopg (Alembic migrations)."""
    if not needs_ssl(url):
        return {}
    # libpq: require = SSL on, no cert verification (unlike verify-ca / verify-full)
    return {"sslmode": "require"}
