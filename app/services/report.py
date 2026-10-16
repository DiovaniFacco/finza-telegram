"""Build summaries and PDF reports."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import repository as repo
from app.models import User
from app.services.charts import category_pie_png, daily_trend_png
from app.services.pdf_theme import (
    ACCENT,
    DIVIDER,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_LIGHT,
    ROW_ALT,
    ROW_TOTAL,
    SURFACE,
    TEXT_ON_PRIMARY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from app.utils.money import format_brl


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _app_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.app_tz)
    except Exception:
        return ZoneInfo("UTC")


def today_in_tz() -> date:
    return datetime.now(_app_timezone()).date()


def month_bounds(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    last_day = calendar.monthrange(d.year, d.month)[1]
    end = d.replace(day=last_day)
    return start, end


# ---------------------------------------------------------------------------
# Summary objects
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Summary:
    label: str
    period_start: date
    period_end: date
    total: Decimal  # total de SAÍDAS (compat)
    total_expense: Decimal
    total_income: Decimal
    total_investment: Decimal
    balance: Decimal
    general_conta: Decimal
    general_dinheiro: Decimal
    general_investido: Decimal
    by_category: list[tuple[str, Decimal]]  # gastos por categoria
    expenses: list  # list[Expense]
    daily: list[tuple[date, Decimal]]


MESES_PT = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def month_label_pt(d: date) -> str:
    return f"{MESES_PT[d.month]} de {d.year}"


async def build_summary(
    session: AsyncSession,
    *,
    user: User,
    start: date,
    end: date,
    label: str,
) -> Summary:
    total_expense = await repo.total_in_range(session, user.id, start, end, kind="expense")
    total_income = await repo.total_in_range(session, user.id, start, end, kind="income")
    total_investment = await repo.total_in_range(session, user.id, start, end, kind="investment")
    by_cat = await repo.totals_by_category(session, user.id, start, end, kind="expense")
    items = await repo.expenses_in_range(session, user.id, start, end)
    series = await repo.daily_totals(session, user.id, start, end, kind="expense")
    balances = await repo.general_balances(session, user.id)
    return Summary(
        label=label,
        period_start=start,
        period_end=end,
        total=total_expense,
        total_expense=total_expense,
        total_income=total_income,
        total_investment=total_investment,
        balance=total_income - total_expense,
        general_conta=balances.get("conta", Decimal("0")),
        general_dinheiro=balances.get("dinheiro", Decimal("0")),
        general_investido=balances.get("investido", Decimal("0")),
        by_category=by_cat,
        expenses=items,
        daily=series,
    )


async def build_today_summary(session: AsyncSession, user: User) -> Summary:
    d = today_in_tz()
    return await build_summary(session, user=user, start=d, end=d, label="Hoje")


async def build_month_summary(session: AsyncSession, user: User) -> Summary:
    d = today_in_tz()
    start, end = month_bounds(d)
    label = month_label_pt(d)
    return await build_summary(session, user=user, start=start, end=end, label=label)


async def build_recent_window(
    session: AsyncSession, user: User, *, days: int = 30
) -> Summary:
    end = today_in_tz()
    start = end - timedelta(days=days - 1)
    return await build_summary(
        session, user=user, start=start, end=end, label=f"Last {days} days"
    )


# ---------------------------------------------------------------------------
# Telegram-friendly text summary
# ---------------------------------------------------------------------------


def format_telegram_summary(summary: Summary, *, header: str | None = None) -> str:
    lines: list[str] = []
    lines.append(header or f"Gastos de {summary.label}")
    lines.append("")
    if not summary.by_category:
        lines.append("Nenhum lançamento registrado.")
        return "\n".join(lines)

    for cat, amt in summary.by_category:
        lines.append(f"{cat}: {format_brl(amt)}")
    lines.append("")
    lines.append(f"💸 Saídas: {format_brl(summary.total_expense)}")
    lines.append(f"💰 Entradas: {format_brl(summary.total_income)}")
    lines.append(f"📈 Investido: {format_brl(summary.total_investment)}")
    lines.append(f"⚖️ Saldo: {format_brl(summary.balance)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF — flat Material Design
# ---------------------------------------------------------------------------


def _material_styles():
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "MaterialTitle",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=TEXT_ON_PRIMARY,
        leading=24,
        spaceAfter=0,
    )
    subtitle = ParagraphStyle(
        "MaterialSubtitle",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#BBDEFB"),  # Blue 100 on primary bar
        leading=14,
        spaceAfter=0,
    )
    section = ParagraphStyle(
        "MaterialSection",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=PRIMARY_DARK,
        spaceBefore=14,
        spaceAfter=8,
        borderPadding=(0, 0, 4, 0),
        borderWidth=0,
        borderColor=PRIMARY,
        leftIndent=0,
    )
    body = ParagraphStyle(
        "MaterialBody",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=TEXT_SECONDARY,
    )
    return title, subtitle, section, body


def _material_header_table(
    report_title: str,
    subtitle_text: str,
    width: float,
    title_style: ParagraphStyle,
    subtitle_style: ParagraphStyle,
) -> Table:
    """Flat Material app bar: solid primary color, white title text."""
    header = Table(
        [
            [Paragraph(report_title, title_style)],
            [Paragraph(subtitle_text, subtitle_style)],
        ],
        colWidths=[width],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (0, 0), 14),
                ("BOTTOMPADDING", (0, 0), (0, 0), 4),
                ("TOPPADDING", (0, 1), (0, 1), 2),
                ("BOTTOMPADDING", (0, 1), (0, 1), 14),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return header


def _material_table_style_header() -> list:
    """Shared flat Material table rules."""
    return [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), TEXT_ON_PRIMARY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("LINEBELOW", (0, 0), (-1, 0), 0, DIVIDER),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT_PRIMARY),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SURFACE, ROW_ALT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, DIVIDER),
    ]


def _summary_table(summary: Summary) -> Table:
    rows: list[list[str]] = [["Categoria", "Valor"]]
    for cat, amt in summary.by_category:
        rows.append([cat, format_brl(amt)])
    rows.append(["Saídas", format_brl(summary.total_expense)])
    rows.append(["Entradas", format_brl(summary.total_income)])
    rows.append(["Investido", format_brl(summary.total_investment)])
    rows.append(["Saldo", format_brl(summary.balance)])
    rows.append(["Conta geral", format_brl(summary.general_conta)])
    rows.append(["Dinheiro geral", format_brl(summary.general_dinheiro)])

    table = Table(rows, colWidths=[10 * cm, 5 * cm])
    style = _material_table_style_header() + [
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), ROW_TOTAL),
        ("TEXTCOLOR", (0, -1), (0, -1), PRIMARY_DARK),
        ("TEXTCOLOR", (1, -1), (1, -1), ACCENT),
        ("LINEABOVE", (0, -1), (-1, -1), 1, PRIMARY),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]
    table.setStyle(TableStyle(style))
    return table


def _expenses_table(summary: Summary) -> Table:
    rows: list[list[str]] = [["Data", "Descrição", "Categoria", "Notas", "Valor"]]
    for e in summary.expenses[:200]:
        _kind = getattr(e, "kind", "expense")
        prefix = {"income": "💰 ", "investment": "📈 "}.get(_kind, "💸 ")
        rows.append(
            [
                e.expense_date.strftime("%d/%m"),
                prefix + (e.merchant or "")[:30],
                e.category or "",
                (e.notes or "")[:36],
                format_brl(e.amount),
            ]
        )
    if len(rows) == 1:
        rows.append(["—", "Nenhum lançamento", "", "", "R$ 0,00"])

    table = Table(
        rows,
        colWidths=[2.0 * cm, 5.5 * cm, 3 * cm, 4.5 * cm, 2.5 * cm],
        repeatRows=1,
    )
    style = _material_table_style_header() + [
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (2, 1), (2, -1), PRIMARY_DARK),
    ]
    table.setStyle(TableStyle(style))
    return table


def _total_chip(summary: Summary, body_style: ParagraphStyle) -> Table:
    """Material-style elevated summary chip for grand total."""
    chip = Table(
        [
            [Paragraph("Saldo do período", body_style)],
            [Paragraph(format_brl(summary.balance), ParagraphStyle(
                "TotalAmount",
                parent=body_style,
                fontName="Helvetica-Bold",
                fontSize=18,
                textColor=PRIMARY_DARK,
                spaceBefore=2,
            ))],
        ],
        colWidths=[15 * cm],
    )
    chip.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PRIMARY_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0, DIVIDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return chip


def _draw_page_background(canvas, doc) -> None:
    """Light grey page background (Material surface)."""
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#FAFAFA"))
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
    canvas.restoreState()


def build_pdf(summary: Summary, *, owner_label: str | None = None) -> bytes:
    title_style, subtitle_style, section_style, body_style = _material_styles()
    buf = BytesIO()

    page_w, _page_h = A4
    margin = 1.6 * cm
    content_width = page_w - 2 * margin

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=1.2 * cm,
        bottomMargin=1.6 * cm,
        title=f"Expense Report — {summary.label}",
    )

    period = (
        summary.period_start.strftime("%d %b %Y")
        if summary.period_start == summary.period_end
        else f"{summary.period_start.strftime('%d %b %Y')} – {summary.period_end.strftime('%d %b %Y')}"
    )
    sub = f"{owner_label + ' · ' if owner_label else ''}{period}"

    story: list = []
    story.append(
        _material_header_table(
            f"Expense Report — {summary.label}",
            sub,
            content_width,
            title_style,
            subtitle_style,
        )
    )
    story.append(Spacer(1, 0.5 * cm))
    story.append(_total_chip(summary, body_style))
    story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph("Summary by category", section_style))
    story.append(_summary_table(summary))

    pie_bytes = category_pie_png(summary.by_category)
    story.append(Spacer(1, 0.45 * cm))
    story.append(Paragraph("Spend by category", section_style))
    story.append(Image(BytesIO(pie_bytes), width=14 * cm, height=9.5 * cm))

    if len(summary.daily) > 1:
        line_bytes = daily_trend_png(summary.daily)
        story.append(Spacer(1, 0.35 * cm))
        story.append(Paragraph("Daily spend", section_style))
        story.append(Image(BytesIO(line_bytes), width=15.5 * cm, height=7.5 * cm))

    story.append(PageBreak())
    story.append(Paragraph("All expenses", section_style))
    story.append(_expenses_table(summary))

    doc.build(
        story,
        onFirstPage=_draw_page_background,
        onLaterPages=_draw_page_background,
    )
    buf.seek(0)
    return buf.getvalue()


def build_csv(summary: Summary) -> bytes:
    """Build a UTF-8 CSV of the expenses in the summary."""
    import csv
    import io

    sio = io.StringIO()
    writer = csv.writer(sio)
    writer.writerow(["Data", "Tipo", "Descrição", "Categoria", "Notas", "Valor"])
    for e in summary.expenses:
        writer.writerow(
            [
                e.expense_date.isoformat(),
                getattr(e, "kind", "expense"),
                e.merchant,
                e.category,
                e.notes or "",
                f"{e.amount:.2f}",
            ]
        )
    return sio.getvalue().encode("utf-8")
