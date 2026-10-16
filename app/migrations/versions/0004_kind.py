"""Coluna kind (expense/income) em expenses.

Revision ID: 0004_kind
Revises: 0003_ptbr_rules
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_kind"
down_revision: str = "0003_ptbr_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="expense"),
    )
    op.create_index("ix_expenses_user_kind", "expenses", ["user_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_expenses_user_kind", table_name="expenses")
    op.drop_column("expenses", "kind")
