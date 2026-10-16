"""Money formatting helpers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def to_decimal(value: float | int | str | Decimal) -> Decimal:
    """Coerce input to a 2-place Decimal, raising on bad data."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as e:  # pragma: no cover - defensive
        raise ValueError(f"Invalid amount: {value!r}") from e
    return d.quantize(Decimal("0.01"))


def format_brl(value: Decimal | float | int | None) -> str:
    """Formata um valor em reais (R$ 3.200,00)."""
    if value is None:
        return "R$ 0,00"
    amount = to_decimal(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    int_part, _, frac_part = f"{amount:.2f}".partition(".")
    # Agrupamento brasileiro (ex: 1.234.567,89)
    grouped = ""
    while len(int_part) > 3:
        grouped = "." + int_part[-3:] + grouped
        int_part = int_part[:-3]
    grouped = int_part + grouped
    return f"{sign}R$ {grouped},{frac_part}"


def format_inr(value: Decimal | float | int | None) -> str:
    """Alias legado — usa formatação BRL."""
    if value is None:
        return "R$ 0,00"
    amount = to_decimal(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    int_part, _, frac_part = f"{amount:.2f}".partition(".")
    grouped = ""
    while len(int_part) > 3:
        grouped = "." + int_part[-3:] + grouped
        int_part = int_part[:-3]
    grouped = int_part + grouped
    return f"{sign}R$ {grouped},{frac_part}"
