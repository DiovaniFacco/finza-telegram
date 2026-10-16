"""Initial schema with users, expenses, category_rules, daily_reports.

Revision ID: 0001_init
Revises:
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEED_RULES: list[tuple[str, str]] = [
    ("uber", "Transport"),
    ("ola", "Transport"),
    ("rapido", "Transport"),
    ("metro", "Transport"),
    ("auto", "Transport"),
    ("swiggy", "Food"),
    ("zomato", "Food"),
    ("dominos", "Food"),
    ("kfc", "Food"),
    ("mcdonalds", "Food"),
    ("starbucks", "Food"),
    ("lunch", "Food"),
    ("breakfast", "Food"),
    ("dinner", "Food"),
    ("coffee", "Food"),
    ("amazon", "Shopping"),
    ("flipkart", "Shopping"),
    ("myntra", "Shopping"),
    ("ajio", "Shopping"),
    ("petrol", "Fuel"),
    ("diesel", "Fuel"),
    ("fuel", "Fuel"),
    ("indian oil", "Fuel"),
    ("hp", "Fuel"),
    ("netflix", "Entertainment"),
    ("spotify", "Entertainment"),
    ("prime", "Entertainment"),
    ("hotstar", "Entertainment"),
    ("bookmyshow", "Entertainment"),
    ("electricity", "Bills"),
    ("water", "Bills"),
    ("gas", "Bills"),
    ("rent", "Bills"),
    ("airtel", "Bills"),
    ("jio", "Bills"),
    ("vodafone", "Bills"),
    ("pharmacy", "Health"),
    ("apollo", "Health"),
    ("medplus", "Health"),
    ("hospital", "Health"),
    ("doctor", "Health"),
    ("blinkit", "Groceries"),
    ("zepto", "Groceries"),
    ("bigbasket", "Groceries"),
    ("dmart", "Groceries"),
    ("grofers", "Groceries"),
    ("groceries", "Groceries"),
]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("merchant", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="Other"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_expenses_user_date", "expenses", ["user_id", "expense_date"])
    op.create_index("ix_expenses_user_category", "expenses", ["user_id", "category"])

    op.create_table(
        "category_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("keyword", sa.String(length=128), nullable=False, unique=True),
        sa.Column("category", sa.String(length=64), nullable=False),
    )

    op.create_table(
        "daily_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "report_date", name="uq_daily_reports_user_date"),
    )

    rules_table = sa.table(
        "category_rules",
        sa.column("keyword", sa.String),
        sa.column("category", sa.String),
    )
    op.bulk_insert(
        rules_table,
        [{"keyword": kw, "category": cat} for kw, cat in SEED_RULES],
    )


def downgrade() -> None:
    op.drop_table("daily_reports")
    op.drop_table("category_rules")
    op.drop_index("ix_expenses_user_category", table_name="expenses")
    op.drop_index("ix_expenses_user_date", table_name="expenses")
    op.drop_table("expenses")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
