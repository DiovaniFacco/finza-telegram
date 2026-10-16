"""Rule-based expense categorization with DB-backed merging."""

from __future__ import annotations

import time
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import all_category_rules

DEFAULT_CATEGORY = "Outros"

# In-process fallback so categorization works even before the DB is reachable.
HARDCODED_RULES: dict[str, str] = {
    # Transporte
    "uber": "Transporte",
    "99": "Transporte",
    "taxi": "Transporte",
    "metro": "Transporte",
    "metrô": "Transporte",
    "onibus": "Transporte",
    "ônibus": "Transporte",
    "gasolina": "Transporte",
    "combustivel": "Transporte",
    "combustível": "Transporte",
    "pedagio": "Transporte",
    "pedágio": "Transporte",
    "estacionamento": "Transporte",
    # Alimentação
    "ifood": "Alimentação",
    "rappi": "Alimentação",
    "lanche": "Alimentação",
    "almoco": "Alimentação",
    "almoço": "Alimentação",
    "jantar": "Alimentação",
    "cafe": "Alimentação",
    "café": "Alimentação",
    "restaurante": "Alimentação",
    "pizza": "Alimentação",
    "lunch": "Alimentação",
    "dinner": "Alimentação",
    "coffee": "Alimentação",
    # Mercado / Compras
    "mercado": "Alimentação",
    "supermercado": "Alimentação",
    "feira": "Alimentação",
    "padaria": "Alimentação",
    "acougue": "Alimentação",
    "açougue": "Alimentação",
    "amazon": "Compras",
    "mercadolivre": "Compras",
    "mercado livre": "Compras",
    "shopee": "Compras",
    "shein": "Compras",
    "roupa": "Compras",
    "shopping": "Compras",
    # Moradia
    "aluguel": "Moradia",
    "condominio": "Moradia",
    "condomínio": "Moradia",
    "financiamento": "Moradia",
    "iptu": "Moradia",
    # Contas
    "luz": "Contas",
    "energia": "Contas",
    "agua": "Contas",
    "água": "Contas",
    "internet": "Contas",
    "telefone": "Contas",
    "celular": "Contas",
    "claro": "Contas",
    "vivo": "Contas",
    "tim": "Contas",
    "oi ": "Contas",
    "electricity": "Contas",
    "rent": "Moradia",
    # Lazer
    "netflix": "Lazer",
    "spotify": "Lazer",
    "prime": "Lazer",
    "cinema": "Lazer",
    "show": "Lazer",
    "jogo": "Lazer",
    "bar": "Lazer",
    "cerveja": "Lazer",
    # Saúde
    "farmacia": "Saúde",
    "farmácia": "Saúde",
    "remedio": "Saúde",
    "remédio": "Saúde",
    "medico": "Saúde",
    "médico": "Saúde",
    "dentista": "Saúde",
    "exame": "Saúde",
    "plano de saude": "Saúde",
    "pharmacy": "Saúde",
    "doctor": "Saúde",
    # Educação
    "escola": "Educação",
    "faculdade": "Educação",
    "curso": "Educação",
    "livro": "Educação",
    "mensalidade": "Educação",
    # Receitas
    "salario": "Salário",
    "salário": "Salário",
    "pagamento": "Salário",
    "freelance": "Freelance",
    "freela": "Freelance",
    "bico": "Freelance",
    # Investimentos
    "tesouro": "Investimento",
    "cdb": "Investimento",
    "lci": "Investimento",
    "lca": "Investimento",
    "fii": "Investimento",
    "fiis": "Investimento",
    "acao": "Investimento",
    "acoes": "Investimento",
    "ação": "Investimento",
    "ações": "Investimento",
    "bolsa": "Investimento",
    "corretora": "Investimento",
    "previdencia": "Investimento",
    "previdência": "Investimento",
    "cripto": "Investimento",
    "bitcoin": "Investimento",
    "ethereum": "Investimento",
    "investimento": "Investimento",
    "aporte": "Investimento",
    "dividendo": "Investimento",
    "rendimento": "Investimento",
}


class CategoryResolver:
    """Caches DB-backed rules and merges them with hardcoded defaults."""

    _CACHE_TTL_SECONDS = 300

    def __init__(self) -> None:
        self._rules: dict[str, str] = dict(HARDCODED_RULES)
        self._loaded_at: float = 0.0

    async def refresh(self, session: AsyncSession) -> None:
        rules = await all_category_rules(session)
        merged = dict(HARDCODED_RULES)
        for r in rules:
            merged[r.keyword.lower()] = r.category
        self._rules = merged
        self._loaded_at = time.monotonic()

    async def ensure_fresh(self, session: AsyncSession) -> None:
        if time.monotonic() - self._loaded_at > self._CACHE_TTL_SECONDS:
            try:
                await self.refresh(session)
            except Exception:
                # On DB failure, keep the in-memory rules; categorization is best-effort.
                pass

    def categorize(self, text: str) -> str:
        return categorize_text(text, self._rules)


def categorize_text(text: str, rules: dict[str, str] | None = None) -> str:
    """Return the first matching category for any keyword found in `text`."""
    rules = rules or HARDCODED_RULES
    if not text:
        return DEFAULT_CATEGORY
    lowered = text.lower()
    for keyword, category in _sorted_by_length(rules):
        if keyword in lowered:
            return category
    return DEFAULT_CATEGORY


def _sorted_by_length(rules: dict[str, str]) -> Iterable[tuple[str, str]]:
    """Longer keywords first to avoid `hp` matching inside `shopping` etc."""
    return sorted(rules.items(), key=lambda kv: -len(kv[0]))


resolver = CategoryResolver()
