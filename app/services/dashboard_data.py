"""Load overview dashboard data (plain dicts, safe after DB session closes)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.models import User
from app.services.report import month_bounds, today_in_tz
from app.utils.money import format_brl


@dataclass(slots=True)
class OverviewData:
    today_total: str
    today_count: int
    month_total: str
    month_income: str
    month_invested: str
    month_balance: str
    conta_geral: str
    dinheiro_geral: str
    investido_total: str
    month_label: str
    top_category: str | None
    top_category_amount: str
    categories: list[tuple[str, str, float]]
    recent: list[dict[str, str]]


async def load_overview(session: AsyncSession, user: User) -> OverviewData:
    """Fetch overview metrics without loading full Summary/daily series."""
    today = today_in_tz()
    month_start, month_end = month_bounds(today)
    from app.services.report import month_label_pt
    month_label = month_label_pt(today)

    today_total_val = await repo.total_in_range(session, user.id, today, today, kind="expense")
    month_total_val = await repo.total_in_range(session, user.id, month_start, month_end, kind="expense")
    month_income_val = await repo.total_in_range(session, user.id, month_start, month_end, kind="income")
    month_invested_val = await repo.total_in_range(session, user.id, month_start, month_end, kind="investment")
    today_items = await repo.expenses_in_range(session, user.id, today, today)
    by_cat = await repo.totals_by_category(session, user.id, month_start, month_end, kind="expense")
    recent_orm = await repo.recent_expenses(session, user.id, limit=10)
    balances = await repo.general_balances(session, user.id)

    top_category = by_cat[0] if by_cat else None
    total = month_total_val or Decimal("0")
    categories = [
        (
            cat,
            format_brl(amount),
            float(amount) / float(total) * 100 if total > 0 else 0.0,
        )
        for cat, amount in by_cat[:6]
    ]

    recent = [
        {
            "expense_date": e.expense_date.strftime("%d/%m"),
            "merchant": ({"income": "💰 ", "investment": "📈 "}.get(e.kind, "💸 ") + (e.merchant or "")),
            "category": e.category or "Outros",
            "kind": e.kind,
            "amount": format_brl(e.amount),
        }
        for e in recent_orm
    ]

    return OverviewData(
        today_total=format_brl(today_total_val),
        today_count=len(today_items),
        month_total=format_brl(month_total_val),
        month_income=format_brl(month_income_val),
        month_invested=format_brl(month_invested_val),
        month_balance=format_brl(month_income_val - month_total_val),
        conta_geral=format_brl(balances.get("conta", 0)),
        dinheiro_geral=format_brl(balances.get("dinheiro", 0)),
        investido_total=format_brl(balances.get("investido", 0)),
        month_label=month_label,
        top_category=top_category[0] if top_category else None,
        top_category_amount=format_brl(top_category[1]) if top_category else "",
        categories=categories,
        recent=recent,
    )


def empty_overview() -> OverviewData:
    """Fallback when DB queries fail — still show a usable dashboard."""
    return OverviewData(
        today_total=format_brl(0),
        today_count=0,
        month_total=format_brl(0),
        month_income=format_brl(0),
        month_invested=format_brl(0),
        month_balance=format_brl(0),
        conta_geral=format_brl(0),
        dinheiro_geral=format_brl(0),
        investido_total=format_brl(0),
        month_label="Este mês",
        top_category=None,
        top_category_amount="",
        categories=[],
        recent=[],
    )
