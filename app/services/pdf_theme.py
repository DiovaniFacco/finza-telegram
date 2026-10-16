"""Flat Material Design tokens for PDF reports and charts."""

from __future__ import annotations

from reportlab.lib import colors

# Material Design 2 palette (flat, no gradients)
PRIMARY = colors.HexColor("#1976D2")  # Blue 700
PRIMARY_LIGHT = colors.HexColor("#E3F2FD")  # Blue 50
PRIMARY_DARK = colors.HexColor("#1565C0")  # Blue 800
ACCENT = colors.HexColor("#FF5722")  # Deep Orange 500

BACKGROUND = colors.HexColor("#FAFAFA")  # Grey 50
SURFACE = colors.white
DIVIDER = colors.HexColor("#E0E0E0")  # Grey 300

TEXT_PRIMARY = colors.HexColor("#212121")  # Grey 900
TEXT_SECONDARY = colors.HexColor("#757575")  # Grey 600
TEXT_ON_PRIMARY = colors.white

ROW_ALT = colors.HexColor("#F5F5F5")  # Grey 100
ROW_TOTAL = colors.HexColor("#E8EAF6")  # Indigo 50 (subtle total highlight)

# Flat chart colors (Material 500 series)
CHART_PALETTE = [
    "#2196F3",  # Blue
    "#4CAF50",  # Green
    "#FF9800",  # Orange
    "#9C27B0",  # Purple
    "#009688",  # Teal
    "#E91E63",  # Pink
    "#3F51B5",  # Indigo
    "#FF5722",  # Deep Orange
    "#00BCD4",  # Cyan
    "#FFC107",  # Amber
]

# Matplotlib hex equivalents
CHART_PRIMARY = "#1976D2"
CHART_GRID = "#EEEEEE"
CHART_TEXT = "#424242"
CHART_SURFACE = "#FFFFFF"
