"""Dashboard pages, JSON stats endpoint, and PDF/CSV exports."""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.db.session import get_session
from app.models import DailyReport, User
from app.services import auth as auth_service
from app.services import dashboard_data
from app.services import report as report_service
from app.utils.logging import get_logger
from app.utils.money import format_brl

logger = get_logger(__name__)

SessionCookie = Annotated[str | None, Cookie(alias=auth_service.SESSION_COOKIE_NAME)]

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _render_template(name: str, context: dict[str, Any]) -> HTMLResponse:
    """Render while request context is active (avoids detached ORM in templates)."""
    template = templates.env.get_template(name)
    html = template.render(context)
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def require_user(
    expense_session: SessionCookie = None,
    session: AsyncSession = Depends(get_session),
) -> User:
    current = auth_service.read_session_cookie(expense_session)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not_authenticated",
        )
    user = await repo.get_user(session, current.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="user_missing"
        )
    return user


def _redirect_to_login() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


def _overview_context(request: Request, user: User, data: dashboard_data.OverviewData) -> dict[str, Any]:
    return {
        "request": request,
        "user": {"first_name": user.first_name, "username": user.username},
        "today_total": data.today_total,
        "today_count": data.today_count,
        "month_total": data.month_total,
        "month_income": data.month_income,
        "month_invested": data.month_invested,
        "month_balance": data.month_balance,
        "conta_geral": data.conta_geral,
        "dinheiro_geral": data.dinheiro_geral,
        "investido_total": data.investido_total,
        "month_label": data.month_label,
        "top_category": data.top_category,
        "top_category_amount": data.top_category_amount,
        "categories": data.categories,
        "recent": data.recent,
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def overview(
    request: Request,
    session: AsyncSession = Depends(get_session),
    expense_session: SessionCookie = None,
):
    user = await _user_or_none(session, expense_session)
    if user is None:
        return _redirect_to_login()

    try:
        data = await dashboard_data.load_overview(session, user)
    except Exception:
        logger.exception("overview_load_failed", user_id=str(user.id))
        data = dashboard_data.empty_overview()

    return _render_template("overview.html", _overview_context(request, user, data))


@router.get("/charts", response_class=HTMLResponse)
async def charts_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    expense_session: SessionCookie = None,
):
    user = await _user_or_none(session, expense_session)
    if user is None:
        return _redirect_to_login()
    return _render_template(
        "charts.html",
        {"request": request, "user": {"first_name": user.first_name}},
    )


@router.get("/expenses", response_class=HTMLResponse)
async def expenses_page(
    request: Request,
    q: str | None = None,
    sort: str = "date",
    dir: str = "desc",
    page: int = Query(default=1, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    expense_session: SessionCookie = None,
):
    user = await _user_or_none(session, expense_session)
    if user is None:
        return _redirect_to_login()

    page_size = 25
    rows, total = await repo.search_expenses(
        session,
        user.id,
        query=q,
        sort=sort,
        direction=dir,
        page=page,
        page_size=page_size,
    )
    pages = max(1, math.ceil(total / page_size))

    expenses = [
        {
            "expense_date": e.expense_date.strftime("%d/%m/%Y"),
            "merchant": e.merchant,
            "category": e.category,
            "kind": e.kind,
            "kind_label": {
                "income": "Entrada",
                "investment": "Investimento",
                "investment_out": "Resgate",
                "transfer_in": "Transferência",
                "transfer_out": "Transferência",
            }.get(e.kind, "Gasto"),
            "notes": e.notes or "",
            "amount": format_brl(e.amount),
        }
        for e in rows
    ]

    return _render_template(
        "expenses.html",
        {
            "request": request,
            "user": {"first_name": user.first_name},
            "expenses": expenses,
            "total": total,
            "page": page,
            "pages": pages,
            "query": q,
            "sort": sort,
            "direction": dir,
        },
    )


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    expense_session: SessionCookie = None,
):
    user = await _user_or_none(session, expense_session)
    if user is None:
        return _redirect_to_login()

    month = await report_service.build_month_summary(session, user)
    result = await session.execute(
        select(DailyReport)
        .where(DailyReport.user_id == user.id)
        .order_by(desc(DailyReport.report_date))
        .limit(10)
    )
    reports = list(result.scalars().all())
    report_rows = [
        {
            "report_date": r.report_date.strftime("%d %b %Y"),
            "total_amount": format_brl(r.total_amount),
        }
        for r in reports
    ]

    return _render_template(
        "reports.html",
        {
            "request": request,
            "user": {"first_name": user.first_name},
            "month_label": month.label,
            "reports": report_rows,
        },
    )


# ---------------------------------------------------------------------------
# JSON stats
# ---------------------------------------------------------------------------


@router.get("/api/stats")
async def api_stats(
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    end = report_service.today_in_tz()
    start_30 = end - timedelta(days=29)

    daily = await repo.daily_totals(session, user.id, start_30, end)
    by_cat = await repo.totals_by_category(session, user.id, start_30, end)
    monthly = await repo.monthly_series(session, user.id, months=6)
    cumulative = await repo.cumulative_balance(session, user.id, days=30)
    merchants = await repo.top_merchants(session, user.id, days=30, limit=8)
    wallets = await repo.wallet_split(session, user.id, days=30)

    weeks: list[dict] = []
    for i in range(7, -1, -1):
        wk_end = end - timedelta(days=i * 7)
        wk_start = wk_end - timedelta(days=6)
        total = await repo.total_in_range(session, user.id, wk_start, wk_end, kind="expense")
        weeks.append(
            {
                "label": wk_start.strftime("%d/%m"),
                "amount": float(total),
            }
        )

    return {
        "categories": [
            {"name": cat, "amount": float(amount)} for cat, amount in by_cat
        ],
        "daily": [
            {"date": d.strftime("%d/%m"), "amount": float(amt)} for d, amt in daily
        ],
        "weekly": weeks,
        "monthly": monthly,
        "cumulative": cumulative,
        "merchants": merchants,
        "wallets": wallets,
    }


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def _resolve_range(range_: str, today: date) -> tuple[date, date, str]:
    if range_ == "today":
        return today, today, "Today"
    if range_ == "all":
        return date(2000, 1, 1), today, "All time"
    start, end = report_service.month_bounds(today)
    label = report_service.month_label_pt(today)
    return start, end, label


@router.get("/export.pdf")
async def export_pdf(
    range: str = "month",
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    today = report_service.today_in_tz()
    start, end, label = _resolve_range(range, today)
    summary = await report_service.build_summary(
        session, user=user, start=start, end=end, label=label
    )
    pdf = report_service.build_pdf(
        summary, owner_label=user.first_name or user.username
    )
    filename = f"expenses-{label.replace(' ', '-')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export.csv")
async def export_csv(
    range: str = "month",
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    today = report_service.today_in_tz()
    start, end, label = _resolve_range(range, today)
    summary = await report_service.build_summary(
        session, user=user, start=start, end=end, label=label
    )
    csv_bytes = report_service.build_csv(summary)
    filename = f"expenses-{label.replace(' ', '-')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _user_or_none(
    session: AsyncSession, cookie_value: str | None
) -> User | None:
    current = auth_service.read_session_cookie(cookie_value)
    if current is None:
        return None
    return await repo.get_user(session, current.user_id)
