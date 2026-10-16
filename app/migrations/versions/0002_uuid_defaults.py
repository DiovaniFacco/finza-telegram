"""Add Postgres UUID defaults so raw INSERTs without id still work.

Revision ID: 0002_uuid_defaults
Revises: 0001_init
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_uuid_defaults"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    for table in ("users", "expenses", "daily_reports"):
        op.execute(
            f'ALTER TABLE {table} ALTER COLUMN id SET DEFAULT gen_random_uuid()'
        )


def downgrade() -> None:
    for table in ("users", "expenses", "daily_reports"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT")
