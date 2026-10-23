"""Agrupa as duas pernas de transferências internas.

Revision ID: 0006_transfer_id
Revises: 0005_wallets
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_transfer_id"
down_revision: str = "0005_wallets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_expenses_user_transfer", "expenses", ["user_id", "transfer_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_expenses_user_transfer", table_name="expenses")
    op.drop_column("expenses", "transfer_id")
