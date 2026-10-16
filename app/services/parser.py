"""Hybrid expense parser: regex -> rules -> AI fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import dateparser
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services import ai as ai_service
from app.services.categorizer import DEFAULT_CATEGORY, resolver
from app.utils.logging import get_logger
from app.utils.money import to_decimal

logger = get_logger(__name__)


# Qualquer token numérico (R$ e centavos com vírgula tratados em _parse_br_number).
_AMOUNT_PATTERN = re.compile(
    r"(\d[\d.,]*\d|\d)",
)

# Tokens que nunca devem virar nome do estabelecimento.
_STOP_WORDS = {
    "for", "on", "at", "of", "the", "a", "an", "spent", "paid", "bought", "got",
    "de", "do", "da", "dos", "das", "no", "na", "nos", "nas", "em", "um", "uma",
    "com", "por", "para", "pra", "pro", "que", "e", "o", "os", "as",
    "gastei", "gastou", "gasto", "paguei", "pagou", "pagar", "comprei", "compra",
    "recebi", "recebeu", "ganhei", "entrou",
    "investi", "investiu", "investir", "aportei", "aportou", "aportar",
    "r$", "rs", "reais", "real", "reai",
}

_DATE_HINTS = re.compile(
    r"\b(hoje|ontem|anteontem|"
    r"today|yesterday|tomorrow|day before yesterday|"
    r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
    r"\d{1,2}\s+(?:jan|fev|feb|mar|abr|apr|mai|may|jun|jul|ago|aug|set|sep|out|oct|nov|dez|dec)[a-z]*"
    r"(?:\s+\d{2,4})?)\b",
    flags=re.IGNORECASE,
)


@dataclass(slots=True)
class ParsedExpense:
    merchant: str
    amount: Decimal
    category: str
    notes: str
    expense_date: date
    source: str  # "regex" | "ai" | "manual"
    kind: str = "expense"  # "expense" | "income" | "investment"
    wallet: str = "conta"  # "conta" | "dinheiro"


_WALLET_PATTERN = re.compile(
    r"\b(em dinheiro( vivo)?|no dinheiro|em espécie|em especie|em cash|no cash|"
    r"dinheiro vivo|dinheiro|espécie|especie)\b",
    flags=re.IGNORECASE,
)


_INCOME_HINTS = {
    "recebi", "recebeu", "recebimento", "ganhei", "ganhou", "salario", "salário",
    "pagamento", "entrou", "entrada", "rendimento", "rendimentos", "dividendo",
    "freelance", "freela", "bico", "caiu", "depositaram", "depositou",
}

_INVEST_HINTS = {
    "investi", "investimento", "investimentos", "aporte", "aportes", "aportei",
    "tesouro", "cdb", "lci", "lca", "acao", "ação", "acoes", "ações", "fii",
    "fiis", "fundo", "fundos", "previdencia", "previdência", "cripto", "bitcoin",
    "ethereum", "renda fixa", "renda variavel", "corretora", "xp ", "nu invest",
}


def _detect_kind(text: str) -> str:
    lowered = text.lower()
    if any(h in lowered for h in _INVEST_HINTS):
        return "investment"
    if any(h in lowered for h in _INCOME_HINTS):
        return "income"
    return "expense"


def _today_local() -> date:
    return datetime.now(ZoneInfo(settings.app_tz)).date()


def _extract_date(text: str) -> tuple[date, str]:
    """Return (resolved_date, text_with_date_removed)."""
    match = _DATE_HINTS.search(text)
    if not match:
        return _today_local(), text

    raw = match.group(0)
    parsed = dateparser.parse(
        raw,
        languages=["pt", "en"],
        settings={
            "TIMEZONE": settings.app_tz,
            "RETURN_AS_TIMEZONE_AWARE": False,
            "PREFER_DATES_FROM": "past",
        },
    )
    if parsed is None:
        return _today_local(), text

    cleaned = (text[: match.start()] + " " + text[match.end() :]).strip()
    return parsed.date(), cleaned


def _parse_br_number(raw: str) -> Decimal | None:
    """Interpreta número nos formatos BR (1.234,56) e US (1234.56)."""
    s = raw.strip()
    if not s:
        return None
    try:
        if "," in s:
            # Formato BR: pontos são milhar, vírgula é decimal
            s = s.replace(".", "").replace(",", ".")
        elif s.count(".") > 1:
            s = s.replace(".", "")
        return Decimal(s)
    except Exception:
        return None


def _extract_amount(text: str) -> tuple[Decimal | None, str]:
    """Return (amount, text_with_amount_token_removed). Prefer the largest match."""
    matches = list(_AMOUNT_PATTERN.finditer(text))
    if not matches:
        return None, text

    # Filter out empty matches (the regex can match a stray currency symbol with empty digits).
    candidates: list[tuple[Decimal, re.Match[str]]] = []
    for m in matches:
        value = _parse_br_number(m.group(1))
        if value is None:
            continue
        candidates.append((value, m))

    if not candidates:
        return None, text

    # Pick the largest numeric value (handles "Amazon mouse 799" reliably).
    value, m = max(candidates, key=lambda c: c[0])
    cleaned = (text[: m.start()] + " " + text[m.end() :]).strip()
    return value, cleaned


def _extract_merchant(text: str) -> str:
    tokens = [t for t in re.split(r"\s+", text) if t]
    cleaned = [t.strip(".,;:!?-") for t in tokens]
    cleaned = [t for t in cleaned if t and t.lower() not in _STOP_WORDS]
    if not cleaned:
        return ""
    return " ".join(cleaned)[:255]


async def parse_expense(message: str, session: AsyncSession) -> ParsedExpense | None:
    """Parse a free-text expense message. Returns None when nothing usable is found."""

    text = message.strip()
    if not text:
        return None

    await resolver.ensure_fresh(session)

    wallet = "dinheiro" if _WALLET_PATTERN.search(text) else "conta"
    text = _WALLET_PATTERN.sub(" ", text).strip()

    expense_date, remainder = _extract_date(text)
    kind = _detect_kind(text)
    amount, remainder = _extract_amount(remainder)
    merchant = _extract_merchant(remainder)
    if not merchant and wallet == "dinheiro":
        merchant = "Dinheiro"

    if amount is not None and amount > 0 and merchant:
        category = resolver.categorize(merchant) or DEFAULT_CATEGORY
        return ParsedExpense(
            merchant=merchant.title(),
            amount=to_decimal(amount),
            category=category,
            notes="",
            expense_date=expense_date,
            source="regex",
            kind=kind,
            wallet=wallet,
        )

    # Fallback to AI parsing only when regex/rules did not yield an actionable expense.
    ai = await ai_service.parse_with_ai(text)
    if ai is None or ai.amount <= 0 or not ai.merchant:
        logger.info("parser_failed", message=text)
        return None

    ai_kind = (ai.kind or "").strip().lower()
    if ai_kind not in ("income", "expense", "investment"):
        ai_kind = kind
    category = ai.category or resolver.categorize(ai.merchant) or DEFAULT_CATEGORY
    return ParsedExpense(
        merchant=ai.merchant.title()[:255],
        amount=to_decimal(ai.amount),
        category=category,
        notes=ai.notes,
        expense_date=expense_date,
        source="ai",
        kind=ai_kind,
        wallet=wallet,
    )
