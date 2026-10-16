"""Data-access helpers for users and expenses."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CategoryRule, DailyReport, Expense, InitialBalance, User

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


async def upsert_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
) -> User:
    """Insert or update a user by telegram_id and return the row."""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        session.add(user)
    else:
        user.username = username
        user.first_name = first_name
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def list_users_with_today_expenses(session: AsyncSession, today: date) -> Sequence[User]:
    """Users who have at least one expense recorded for the given date."""
    stmt = (
        select(User)
        .join(Expense, Expense.user_id == User.id)
        .where(Expense.expense_date == today)
        .group_by(User.id)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Category rules
# ---------------------------------------------------------------------------


async def all_category_rules(session: AsyncSession) -> list[CategoryRule]:
    result = await session.execute(select(CategoryRule))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


async def create_expense(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    merchant: str,
    amount: Decimal,
    category: str,
    notes: str | None,
    expense_date: date,
    kind: str = "expense",
    wallet: str = "conta",
) -> Expense:
    expense = Expense(
        user_id=user_id,
        merchant=merchant,
        amount=amount,
        category=category,
        notes=notes,
        expense_date=expense_date,
        kind=kind,
        wallet=wallet,
    )
    session.add(expense)
    await session.commit()
    await session.refresh(expense)
    return expense


def _date_filter(user_id: uuid.UUID, start: date, end: date, kind: str | None = None,
                 wallet: str | None = None):
    conds = [
        Expense.user_id == user_id,
        Expense.expense_date >= start,
        Expense.expense_date <= end,
    ]
    if kind is not None:
        conds.append(Expense.kind == kind)
    if wallet is not None:
        conds.append(Expense.wallet == wallet)
    return and_(*conds)


async def expenses_in_range(
    session: AsyncSession,
    user_id: uuid.UUID,
    start: date,
    end: date,
    kind: str | None = None,
    wallet: str | None = None,
) -> list[Expense]:
    stmt = (
        select(Expense)
        .where(_date_filter(user_id, start, end, kind, wallet))
        .order_by(desc(Expense.expense_date), desc(Expense.created_at))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def total_in_range(
    session: AsyncSession, user_id: uuid.UUID, start: date, end: date,
    kind: str | None = None,
    wallet: str | None = None,
) -> Decimal:
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        _date_filter(user_id, start, end, kind, wallet)
    )
    result = await session.execute(stmt)
    return Decimal(result.scalar_one())


async def totals_by_category(
    session: AsyncSession, user_id: uuid.UUID, start: date, end: date,
    kind: str | None = "expense",
) -> list[tuple[str, Decimal]]:
    stmt = (
        select(Expense.category, func.coalesce(func.sum(Expense.amount), 0))
        .where(_date_filter(user_id, start, end, kind))
        .group_by(Expense.category)
        .order_by(desc(func.sum(Expense.amount)))
    )
    result = await session.execute(stmt)
    return [(row[0], Decimal(row[1])) for row in result.all()]


async def daily_totals(
    session: AsyncSession, user_id: uuid.UUID, start: date, end: date,
    kind: str | None = "expense",
) -> list[tuple[date, Decimal]]:
    stmt = (
        select(Expense.expense_date, func.coalesce(func.sum(Expense.amount), 0))
        .where(_date_filter(user_id, start, end, kind))
        .group_by(Expense.expense_date)
        .order_by(Expense.expense_date.asc())
    )
    result = await session.execute(stmt)
    rows = [(row[0], Decimal(row[1])) for row in result.all()]
    by_date = dict(rows)
    out: list[tuple[date, Decimal]] = []
    cur = start
    while cur <= end:
        out.append((cur, by_date.get(cur, Decimal("0"))))
        cur += timedelta(days=1)
    return out


async def recent_expenses(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 10,
    kind: str | None = None,
    wallet: str | None = None,
) -> list[Expense]:
    conds = [Expense.user_id == user_id]
    if kind is not None:
        conds.append(Expense.kind == kind)
    if wallet is not None:
        conds.append(Expense.wallet == wallet)
    stmt = (
        select(Expense)
        .where(and_(*conds))
        .order_by(desc(Expense.created_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Séries para gráficos
# ---------------------------------------------------------------------------

MESES_PT_SHORT = ["", "jan", "fev", "mar", "abr", "mai", "jun",
                  "jul", "ago", "set", "out", "nov", "dez"]


async def monthly_series(
    session: AsyncSession, user_id: uuid.UUID, months: int = 6,
) -> list[dict]:
    """Últimos N meses: entradas, saídas e investimentos por mês."""
    from datetime import date as _date

    today = _date.today()
    out = []
    for i in range(months - 1, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        import calendar as _cal
        last = _cal.monthrange(y, m)[1]
        start = _date(y, m, 1)
        end = _date(y, m, last)
        out.append({
            "label": f"{MESES_PT_SHORT[m]}/{str(y)[2:]}",
            "income": float(await total_in_range(session, user_id, start, end, kind="income")),
            "expense": float(await total_in_range(session, user_id, start, end, kind="expense")),
            "investment": float(await total_in_range(session, user_id, start, end, kind="investment")),
        })
    for row in out:
        row["balance"] = row["income"] - row["expense"]
    return out


async def cumulative_balance(
    session: AsyncSession, user_id: uuid.UUID, days: int = 30,
) -> list[dict]:
    """Saldo (entradas−saídas) acumulado dia a dia na janela."""
    from datetime import date as _date
    from datetime import timedelta as _td

    end = _date.today()
    start = end - _td(days=days - 1)
    daily_in = await daily_totals(session, user_id, start, end, kind="income")
    daily_out = await daily_totals(session, user_id, start, end, kind="expense")
    in_map = {d: float(v) for d, v in daily_in}
    out_map = {d: float(v) for d, v in daily_out}
    cum = 0.0
    out = []
    cur = start
    while cur <= end:
        cum += in_map.get(cur, 0.0) - out_map.get(cur, 0.0)
        out.append({"date": cur.strftime("%d/%m"), "balance": round(cum, 2)})
        cur += _td(days=1)
    return out


async def top_merchants(
    session: AsyncSession, user_id: uuid.UUID, days: int = 30, limit: int = 8,
) -> list[dict]:
    from datetime import date as _date
    from datetime import timedelta as _td

    end = _date.today()
    start = end - _td(days=days - 1)
    stmt = (
        select(Expense.merchant, func.coalesce(func.sum(Expense.amount), 0))
        .where(_date_filter(user_id, start, end, kind="expense"))
        .group_by(Expense.merchant)
        .order_by(desc(func.sum(Expense.amount)))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [{"merchant": r[0], "amount": float(r[1])} for r in rows]


async def wallet_split(
    session: AsyncSession, user_id: uuid.UUID, days: int = 30,
) -> list[dict]:
    from datetime import date as _date
    from datetime import timedelta as _td

    end = _date.today()
    start = end - _td(days=days - 1)
    out = []
    for wallet, label in (("conta", "Conta"), ("dinheiro", "Dinheiro")):
        stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
            _date_filter(user_id, start, end, kind="expense", wallet=wallet))
        total = (await session.execute(stmt)).scalar_one()
        out.append({"wallet": label, "amount": float(total)})
    return out


# ---------------------------------------------------------------------------
# Searchable / paginated listing
# ---------------------------------------------------------------------------


SORT_COLUMNS: dict[str, Any] = {
    "date": Expense.expense_date,
    "amount": Expense.amount,
    "merchant": Expense.merchant,
    "category": Expense.category,
}


async def search_expenses(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    query: str | None = None,
    kind: str | None = None,
    wallet: str | None = None,
    sort: str = "date",
    direction: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Expense], int]:
    base: Select[tuple[Expense]] = select(Expense).where(Expense.user_id == user_id)
    if kind is not None:
        base = base.where(Expense.kind == kind)
    if wallet is not None:
        base = base.where(Expense.wallet == wallet)
    if query:
        like = f"%{query.lower()}%"
        base = base.where(
            or_(
                func.lower(Expense.merchant).like(like),
                func.lower(Expense.category).like(like),
                func.lower(func.coalesce(Expense.notes, "")).like(like),
            )
        )

    sort_col = SORT_COLUMNS.get(sort, Expense.expense_date)
    if direction.lower() == "asc":
        ordered = base.order_by(sort_col.asc(), Expense.created_at.asc())
    else:
        ordered = base.order_by(sort_col.desc(), Expense.created_at.desc())

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    page = max(page, 1)
    offset = (page - 1) * page_size
    paginated = ordered.offset(offset).limit(page_size)
    rows = (await session.execute(paginated)).scalars().all()
    return list(rows), int(total)


# ---------------------------------------------------------------------------
# Carteiras e saldos gerais (acumulado, sem zerar no mês)
# ---------------------------------------------------------------------------

WALLETS = ("conta", "dinheiro")


async def set_initial_balance(
    session: AsyncSession, *, user_id: uuid.UUID, wallet: str, amount: Decimal,
) -> InitialBalance:
    result = await session.execute(
        select(InitialBalance).where(
            InitialBalance.user_id == user_id, InitialBalance.wallet == wallet)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = InitialBalance(user_id=user_id, wallet=wallet, amount=amount)
        session.add(row)
    else:
        row.amount = amount
    await session.commit()
    await session.refresh(row)
    return row


async def get_initial_balances(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Decimal]:
    result = await session.execute(
        select(InitialBalance).where(InitialBalance.user_id == user_id))
    return {r.wallet: Decimal(r.amount) for r in result.scalars().all()}


async def wallet_kind_total(
    session: AsyncSession, user_id: uuid.UUID, wallet: str, kind: str,
) -> Decimal:
    """Total acumulado (todas as datas) de um kind numa carteira."""
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.wallet == wallet,
        Expense.kind == kind,
    )
    result = await session.execute(stmt)
    return Decimal(result.scalar_one())


async def general_balances(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Decimal]:
    """Saldos gerais por carteira: inicial + entradas − saídas (investimento não abate)."""
    initials = await get_initial_balances(session, user_id)
    out: dict[str, Decimal] = {}
    for wallet in WALLETS:
        income = await wallet_kind_total(session, user_id, wallet, "income")
        expense = await wallet_kind_total(session, user_id, wallet, "expense")
        out[wallet] = Decimal(initials.get(wallet, 0)) + income - expense
    invested = Decimal("0")
    for wallet in WALLETS:
        invested += await wallet_kind_total(session, user_id, wallet, "investment")
    out["investido"] = invested
    return out


# ---------------------------------------------------------------------------
# Daily reports
# ---------------------------------------------------------------------------


async def upsert_daily_report(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    report_date: date,
    total_amount: Decimal,
    pdf_path: str | None,
) -> DailyReport:
    result = await session.execute(
        select(DailyReport).where(
            DailyReport.user_id == user_id,
            DailyReport.report_date == report_date,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = DailyReport(
            user_id=user_id,
            report_date=report_date,
            total_amount=total_amount,
            pdf_path=pdf_path,
        )
        session.add(row)
    else:
        row.total_amount = total_amount
        row.pdf_path = pdf_path
    await session.commit()
    await session.refresh(row)
    return row
