"""Chart rendering for PDF reports — flat Material Design style."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

import matplotlib

matplotlib.use("Agg")  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

from app.services.pdf_theme import (
    CHART_GRID,
    CHART_PALETTE,
    CHART_PRIMARY,
    CHART_SURFACE,
    CHART_TEXT,
)


def _material_axes_style() -> None:
    """Flat Material chart defaults: clean axes, no chart junk."""
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.facecolor": CHART_SURFACE,
            "axes.edgecolor": CHART_GRID,
            "axes.labelcolor": CHART_TEXT,
            "axes.titlecolor": CHART_TEXT,
            "axes.titleweight": "medium",
            "axes.titlesize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.spines.bottom": True,
            "xtick.color": CHART_TEXT,
            "ytick.color": CHART_TEXT,
            "figure.facecolor": CHART_SURFACE,
            "grid.color": CHART_GRID,
            "grid.linewidth": 0.8,
        }
    )


def category_pie_png(totals: list[tuple[str, Decimal]]) -> bytes:
    _material_axes_style()
    if not totals:
        totals = [("Sem dados", Decimal("1"))]

    labels = [t[0] for t in totals]
    values = [float(t[1]) for t in totals]
    slice_colors = [CHART_PALETTE[i % len(CHART_PALETTE)] for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(5.5, 4), dpi=140)
    wedges, _texts, autotexts = ax.pie(
        values,
        labels=None,
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 5 else "",
        colors=slice_colors,
        startangle=90,
        pctdistance=0.75,
        wedgeprops={"linewidth": 1, "edgecolor": CHART_SURFACE},
    )
    for txt in autotexts:
        txt.set_color("white")
        txt.set_fontsize(9)
        txt.set_fontweight("medium")
    ax.set_title("Gastos por categoria", pad=12, color=CHART_TEXT)
    ax.legend(
        wedges,
        labels,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=True,
        fancybox=False,
        edgecolor=CHART_GRID,
        facecolor=CHART_SURFACE,
        fontsize=9,
    )

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=CHART_SURFACE)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def daily_trend_png(series: list[tuple[date, Decimal]]) -> bytes:
    """Flat Material bar chart for daily spend (no gradient fill)."""
    _material_axes_style()
    if not series:
        series = [(date.today(), Decimal("0"))]

    xs = [d for d, _ in series]
    ys = [float(v) for _, v in series]

    fig, ax = plt.subplots(figsize=(7, 3.5), dpi=140)
    bars = ax.bar(
        xs,
        ys,
        color=CHART_PRIMARY,
        width=0.65,
        edgecolor=CHART_PRIMARY,
        linewidth=0,
        alpha=1.0,
    )
    for bar, val in zip(bars, ys, strict=True):
        if val > 0:
            bar.set_alpha(0.85)

    ax.set_title("Gastos por dia", pad=12, color=CHART_TEXT)
    ax.set_ylabel("Valor (R$)", color=CHART_TEXT)
    ax.yaxis.grid(True, linestyle="-", color=CHART_GRID, alpha=1.0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", rotation=30)
    fig.autofmt_xdate(rotation=30)

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=CHART_SURFACE)
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
