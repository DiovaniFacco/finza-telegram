"""Carteiras (conta/dinheiro) + saldos iniciais.

Revision ID: 0005_wallets
Revises: 0004_kind
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_wallets"
down_revision: str = "0004_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column("wallet", sa.String(length=16), nullable=False, server_default="conta"),
    )
    op.create_index("ix_expenses_user_wallet", "expenses", ["user_id", "wallet"])
    op.create_table(
        "initial_balances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wallet", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "wallet", name="uq_initial_balances_user_wallet"),
    )


def downgrade() -> None:
    op.drop_table("initial_balances")
    op.drop_index("ix_expenses_user_wallet", table_name="expenses")
    op.drop_column("expenses", "wallet")
