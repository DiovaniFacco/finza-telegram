"""Hybrid parser: regex -> rules -> AI fallback.

Além de lançamentos novos (gasto/entrada/aporte), o parser reconhece operações:
- ``delete``: apagar/remover/desfazer um lançamento existente;
- ``transfer``: mover dinheiro entre conta, dinheiro e investimentos
  (inclui resgates de investimento).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    # Verbos/termos de operação (não são estabelecimento)
    "removi", "remove", "remover", "removeu", "remova", "removam", "removido",
    "apaga", "apago", "apague", "apagar", "apagou", "apagado",
    "exclui", "excluo", "excluir", "exclua", "excluiu", "excluído", "excluido",
    "deleta", "deleto", "deletar", "delete", "deletou",
    "desfaz", "desfazer", "desfaça", "desfaco", "desfez",
    "cancela", "cancelo", "cancelar", "cancele", "cancelou",
    "resgata", "resgato", "resgatar", "resgatei", "resgatou",
    "retira", "retiro", "retirar", "retirei", "retirou",
    "tira", "tiro", "tirar", "tirei", "tirou",
    "saca", "saco", "sacar", "saquei", "sacou",
    "transfere", "transfiro", "transferir", "transferi", "transferiu",
    "transferência", "transferencia",
    "move", "movo", "mover", "movi", "moveu", "movido",
    "passa", "passo", "passar", "passei", "passou",
    "leva", "levo", "levar", "levei", "levou",
    "coloca", "coloco", "colocar", "coloquei", "colocou",
    "joga", "jogo", "jogar", "joguei", "jogou",
    "deposita", "deposito", "depositar", "depositei", "depositou",
    "manda", "mando", "mandar", "mandei", "mandou",
    "envia", "envio", "enviar", "enviei", "enviou",
    "realoca", "realoco", "realocar", "realoquei", "realocou",
    "aloca", "aloco", "alocar", "aloquei", "alocou",
    "migra", "migro", "migrar", "migrei", "migrou",
    "devolve", "devolvo", "devolver", "devolvi", "devolveu",
    "volta", "volto", "voltar", "voltei", "voltou", "voltam",
    "ultimo", "último", "ultima", "última", "isso", "isto",
    "esse", "essa", "este", "esta", "aquele", "aquela",
    "meu", "minha", "meus", "minhas", "nosso", "nossa", "nossos", "nossas",
    "despesa", "entrada", "receita", "saida", "saída",
}

# Termos que só devem ser ignorados ao extrair o alvo de uma operação
# (não atrapalham a extração de nome em lançamentos novos).
_OPERATION_STOP_WORDS = {
    "conta", "banco", "dinheiro", "espécie", "especie", "cash", "carteira",
    "investimento", "investimentos", "resgate", "resgates", "retirada",
    "lançamento", "lancamento", "registro", "aporte",
    "valor", "valores", "tudo", "todos", "todas",
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
class ParsedOperation:
    """Uma intenção interpretada a partir de uma mensagem livre."""

    action: str = "create"  # "create" | "delete" | "transfer"
    merchant: str = ""
    amount: Decimal | None = None
    category: str = DEFAULT_CATEGORY
    notes: str = ""
    expense_date: date = field(default_factory=lambda: _today_local())
    source: str = "regex"  # "regex" | "ai" | "manual"
    kind: str = "expense"  # "expense" | "income" | "investment"
    wallet: str = "conta"  # criação: carteira; transferência: origem
    wallet_to: str = ""  # transferência: destino (conta/dinheiro/investimento)
    target_kind: str | None = None  # remoção: tipo do lançamento alvo
    latest_only: bool = False  # remoção: sempre o mais recente
    date_explicit: bool = False
    raw: str = ""

    @property
    def is_operation(self) -> bool:
        return self.action in ("delete", "transfer")


# Compatibilidade com o nome antigo.
ParsedExpense = ParsedOperation


_WALLET_PATTERN = re.compile(
    r"\b(em dinheiro( vivo)?|no dinheiro|em espécie|em especie|em cash|no cash|"
    r"dinheiro vivo|dinheiro|espécie|especie)\b",
    flags=re.IGNORECASE,
)


_INCOME_HINTS = {
    "recebi", "recebeu", "recebimento", "ganhei", "ganhou", "salario", "salário",
    "pagamento", "entrou", "entrada", "rendimento", "rendimentos", "dividendo",
    "dividendos", "freelance", "freela", "bico", "caiu", "depositaram", "depositou",
    "depósito", "deposito", "depositei", "estorno", "reembolso",
}

_INVEST_HINTS = {
    "investi", "investimento", "investimentos", "aporte", "aportes", "aportei",
    "tesouro", "cdb", "lci", "lca", "acao", "ação", "acoes", "ações", "fii",
    "fiis", "fundo", "fundos", "previdencia", "previdência", "cripto", "bitcoin",
    "ethereum", "renda fixa", "renda variavel", "corretora", "xp ", "nu invest",
    "apliquei", "aplicação", "aplicacao", "poupança", "poupanca",
}

_INVEST_VERBS = {
    "investi", "investiu", "investir", "aportei", "aportou", "aportar",
    "apliquei", "aplicou", "aplicar", "aloca", "aloquei",
}


# Verbos que indicam operação (e não um lançamento novo).
_DELETE_RE = re.compile(
    r"(?<!\w)(remov\w*|apag\w*|exclu\w*|delet\w*|desf\w+|cancel\w*|errei)(?!\w)",
    re.IGNORECASE,
)
_REDEEM_RE = re.compile(
    r"(?<!\w)(resgat\w*|retir\w*|tir(?:a|ar|e|ei|ou|o|am|aram)|"
    r"sac\w*|withdraw\w*|devolv\w*|volt(?:a|ar|ei|ou|am))(?!\w)",
    re.IGNORECASE,
)
_TRANSFER_RE = re.compile(
    r"(?<!\w)(transfer\w*|mov(?:e|er|i|eu|ido|a|am)|pass(?:a|ar|ei|ou|am)|"
    r"lev(?:a|ar|ei|ou|am)|coloc\w*|jog\w*|deposit\w*|mand\w*|envi\w*|"
    r"realoc\w*|aloc\w*|migr\w*|devolv\w*)(?!\w)",
    re.IGNORECASE,
)

_LATEST_RE = re.compile(
    r"(?<!\w)(últim[oa]|ultim[oa]|isso|isto|esse|essa|este|esta|aquele|aquela)(?!\w)",
    re.IGNORECASE,
)

# "tira o investimento de 500" (objeto direto) costuma significar apagar o
# lançamento — diferente de "tira 500 dos investimentos" (resgate).
_DIRECT_INVEST_DELETE_RE = re.compile(
    r"(?<!\w)(?:remov\w*|apag\w*|exclu\w*|delet\w*|desf\w+|cancel\w*|"
    r"tir\w*|retir\w*)\s+"
    r"(?:o|a|os|as|esse|essa|este|esta|aquele|aquela|meu|minha)\s+"
    r"(?:investimento|investimentos|aporte|lan[cç]amento|registro|resgate)(?!\w)",
    re.IGNORECASE,
)

# Reconhece menções a carteiras/investimentos e a preposição que as antecede.
_WALLET_TOKEN_RE = re.compile(
    r"\b(conta(?:\s+corrente)?|banco|dinheiro(?:\s+vivo)?|esp[eé]cie|cash|carteira|"
    r"investimentos?|invest(?:imento)?|corretora|tesouro(?:\s+direto)?|cdb|lci|lca|"
    r"a[cç][oõ]es|fii|fiis|cripto(?:moedas?)?|bitcoin|ethereum|poupan[cç]a)\b",
    re.IGNORECASE,
)

_SOURCE_PREFIX_RE = re.compile(
    r"(?:\b(?:d[aeo]s?|from)\s+(?:minha\s+|meu\s+|nossa\s+|nosso\s+)?)$",
    re.IGNORECASE,
)
_DEST_PREFIX_RE = re.compile(
    r"(?:\b(?:p[ra]o?s?|para|pra|n[ao]s?|em|aos?|à[s]?|to|into|"
    r"dentro\s+d[ao])\s+(?:(?:o|a|os|as)\s+)?"
    r"(?:minha\s+|meu\s+|nossa\s+|nosso\s+)?)$",
    re.IGNORECASE,
)


def _today_local() -> date:
    return datetime.now(ZoneInfo(settings.app_tz)).date()


def _mentions_any(text: str, hints: set[str]) -> bool:
    """Word-boundary match (evita 'acao' dentro de 'facao', etc.)."""
    lowered = text.lower()
    for hint in hints:
        h = hint.strip()
        if not h:
            continue
        if re.search(rf"(?<!\w){re.escape(h)}(?!\w)", lowered):
            return True
    return False


def _detect_kind(text: str) -> str:
    """Classifica um lançamento novo em income/expense/investment.

    Verbos explícitos de entrada têm prioridade, exceto quando também há verbo
    explícito de aporte. Isso evita que "recebi rendimento do investimento"
    vire um novo aporte.
    """
    lowered = text.lower()
    income_verb = _mentions_any(lowered, _INCOME_HINTS)
    invest_verb = _mentions_any(lowered, _INVEST_VERBS)
    if income_verb and not invest_verb:
        return "income"
    if _mentions_any(lowered, _INVEST_HINTS):
        return "investment"
    if income_verb:
        return "income"
    return "expense"


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


def _extract_merchant(text: str, extra_stop: set[str] | None = None) -> str:
    stop = _STOP_WORDS | (extra_stop or set())
    tokens = [t for t in re.split(r"\s+", text) if t]
    cleaned = [t.strip(".,;:!?-") for t in tokens]
    cleaned = [t for t in cleaned if t and t.lower() not in stop]
    if not cleaned:
        return ""
    return " ".join(cleaned)[:255]


def _wallet_from_token(token: str) -> str:
    t = token.lower()
    if re.match(r"(conta|banco)", t):
        return "conta"
    if re.match(r"(dinheiro|esp|cash|carteira)", t):
        return "dinheiro"
    return "investimento"


def _wallet_roles(text: str) -> tuple[str | None, str | None]:
    """Extrai (origem, destino) a partir das preposições da frase.

    Ex.: "tira 500 dos investimentos e move pra conta" -> ("investimento", "conta").
    """
    sources: list[str] = []
    destinations: list[str] = []
    for match in _WALLET_TOKEN_RE.finditer(text):
        wallet = _wallet_from_token(match.group(0))
        prefix = text[max(0, match.start() - 40) : match.start()]
        if _SOURCE_PREFIX_RE.search(prefix):
            sources.append(wallet)
        elif _DEST_PREFIX_RE.search(prefix):
            destinations.append(wallet)

    source = sources[0] if sources else None
    dest = destinations[0] if destinations else None

    # Sem preposição clara, usa a ordem: primeira carteira = origem.
    if source is None and dest is None:
        wallets = [_wallet_from_token(m.group(0)) for m in _WALLET_TOKEN_RE.finditer(text)]
        if len(wallets) >= 2 and wallets[0] != wallets[1]:
            source, dest = wallets[0], wallets[1]
    return source, dest


def _target_kind_from_text(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"(?<!\w)(resgate|resgates|retirada)(?!\w)", lowered):
        return "investment_out"
    if _mentions_any(lowered, _INVEST_HINTS):
        return "investment"
    if re.search(r"(?<!\w)(entrada|receita|recebimento|sal[aá]rio|dep[oó]sito)(?!\w)", lowered):
        return "income"
    if re.search(r"(?<!\w)(gasto|despesa|sa[ií]da|compra)(?!\w)", lowered):
        return "expense"
    return None


def detect_operation_intent(text: str) -> str | None:
    """Retorna "delete", "transfer" ou None para mensagens de lançamento novo."""
    if _DELETE_RE.search(text):
        return "delete"

    source, dest = _wallet_roles(text)
    if _DIRECT_INVEST_DELETE_RE.search(text) and dest is None:
        return "delete"

    redeem_verb = bool(_REDEEM_RE.search(text))
    resgat = bool(re.search(r"(?<!\w)resgat\w*", text, re.IGNORECASE))
    invest_mentioned = _mentions_any(text, _INVEST_HINTS)
    transfer_verb = bool(_TRANSFER_RE.search(text))

    if redeem_verb or resgat:
        if resgat or invest_mentioned:
            return "transfer"
        if source and dest:
            return "transfer"

    if transfer_verb:
        if invest_mentioned and (source or dest == "investimento"):
            return "transfer"
        if source and dest:
            return "transfer"

    return None


def rule_parse_operation(message: str) -> ParsedOperation | None:
    """Interpreta uma operação sem chamar IA. Retorna None se não for operação."""
    text = message.strip()
    if not text:
        return None

    intent = detect_operation_intent(text)
    if intent is None:
        return None

    expense_date, remainder = _extract_date(text)
    date_explicit = bool(_DATE_HINTS.search(text))
    amount, remainder = _extract_amount(remainder)
    merchant = _extract_merchant(remainder, _OPERATION_STOP_WORDS)
    wallet, wallet_to = _wallet_roles(text)
    latest_only = bool(_LATEST_RE.search(text))

    if intent == "delete":
        target_kind = _target_kind_from_text(text)
        return ParsedOperation(
            action="delete",
            merchant=merchant,
            amount=to_decimal(amount) if amount is not None else None,
            category=DEFAULT_CATEGORY,
            expense_date=expense_date,
            source="regex",
            kind=target_kind or "expense",
            target_kind=target_kind,
            wallet=wallet or "conta",
            latest_only=latest_only,
            date_explicit=date_explicit,
            raw=text,
        )

    # transfer
    if wallet is None:
        if resgat_or_redeem(text) or _mentions_any(text, _INVEST_HINTS):
            wallet = "investimento"
        else:
            wallet = "conta"
    if wallet_to is None:
        if wallet == "investimento":
            wallet_to = "conta"
        else:
            wallet_to = "dinheiro" if wallet == "conta" else "conta"

    return ParsedOperation(
        action="transfer",
        merchant=merchant,
        amount=to_decimal(amount) if amount is not None else None,
        category="Transferência",
        expense_date=expense_date,
        source="regex",
        wallet=wallet,
        wallet_to=wallet_to,
        date_explicit=date_explicit,
        raw=text,
    )


def resgat_or_redeem(text: str) -> bool:
    return bool(re.search(r"(?<!\w)resgat\w*", text, re.IGNORECASE))


def _operation_from_ai(
    ai: ai_service.AIParseResult,
    text: str,
    *,
    expense_date: date,
    date_explicit: bool,
) -> ParsedOperation:
    """Converte a saída da IA em uma operação estruturada."""
    action = ai.action if ai.action in ("create", "delete", "transfer") else "create"
    amount = to_decimal(ai.amount) if ai.amount and ai.amount > 0 else None

    if action == "delete":
        target_kind = ai.target_kind or None
        return ParsedOperation(
            action="delete",
            merchant=ai.merchant,
            amount=amount,
            category=ai.category or DEFAULT_CATEGORY,
            notes=ai.notes,
            expense_date=expense_date,
            source="ai",
            kind=target_kind or ai.kind or "expense",
            target_kind=target_kind,
            latest_only=bool(_LATEST_RE.search(text)),
            date_explicit=date_explicit,
            raw=text,
        )

    if action == "transfer":
        source = ai.from_wallet
        dest = ai.to_wallet
        if not source:
            source = "investimento" if (resgat_or_redeem(text) or dest == "conta") else "conta"
        if not dest:
            dest = "conta" if source == "investimento" else "dinheiro"
        return ParsedOperation(
            action="transfer",
            merchant=ai.merchant,
            amount=amount,
            category="Transferência",
            notes=ai.notes,
            expense_date=expense_date,
            source="ai",
            wallet=source,
            wallet_to=dest,
            date_explicit=date_explicit,
            raw=text,
        )

    ai_kind = ai.kind if ai.kind in ("income", "expense", "investment") else "expense"
    return ParsedOperation(
        action="create",
        merchant=ai.merchant,
        amount=amount,
        category=ai.category or DEFAULT_CATEGORY,
        notes=ai.notes,
        expense_date=expense_date,
        source="ai",
        kind=ai_kind,
        wallet="conta",
        date_explicit=date_explicit,
        raw=text,
    )


async def parse_message(message: str, session: AsyncSession) -> ParsedOperation | None:
    """Interpreta uma mensagem livre como lançamento novo, remoção ou transferência."""
    text = message.strip()
    if not text:
        return None

    await resolver.ensure_fresh(session)

    # Operações primeiro: "investimento" em "removi 500 dos investimentos" não
    # pode virar um novo aporte (bug que motivou esta camada).
    intent = detect_operation_intent(text)
    if intent is not None:
        op = rule_parse_operation(text)

        if op is not None and op.action == "delete":
            # Regras já têm dados fortes: não gasta chamada de IA.
            if op.latest_only or op.amount is not None or op.target_kind is not None:
                return op
            # Remoção vaga ("remove aquele negócio de ontem"): tenta refinar com IA.
            ai = await ai_service.parse_with_ai(text)
            if ai is not None and ai.action == "delete":
                ai_op = _operation_from_ai(
                    ai,
                    text,
                    expense_date=op.expense_date,
                    date_explicit=op.date_explicit,
                )
                if ai_op.amount is not None or ai_op.target_kind or ai_op.merchant:
                    return ai_op
            return op

        if op is not None and op.action == "transfer" and op.amount:
            return op

        # Regras não resolveram: pede ajuda para a IA (se configurada).
        ai = await ai_service.parse_with_ai(text)
        if ai is not None and ai.action in ("delete", "transfer"):
            expense_date, _ = _extract_date(text)
            ai_op = _operation_from_ai(
                ai,
                text,
                expense_date=expense_date,
                date_explicit=bool(_DATE_HINTS.search(text)),
            )
            if op is not None and op.date_explicit and not ai_op.date_explicit:
                ai_op.expense_date = op.expense_date
                ai_op.date_explicit = True
            return ai_op
        if op is not None:
            return op

    wallet = "dinheiro" if _WALLET_PATTERN.search(text) else "conta"
    create_text = _WALLET_PATTERN.sub(" ", text).strip()

    expense_date, remainder = _extract_date(create_text)
    kind = _detect_kind(create_text)
    amount, remainder = _extract_amount(remainder)
    merchant = _extract_merchant(remainder)
    if not merchant and wallet == "dinheiro":
        merchant = "Dinheiro"

    if amount is not None and amount > 0 and merchant:
        category = resolver.categorize(merchant) or DEFAULT_CATEGORY
        return ParsedOperation(
            action="create",
            merchant=merchant.title(),
            amount=to_decimal(amount),
            category=category,
            notes="",
            expense_date=expense_date,
            source="regex",
            kind=kind,
            wallet=wallet,
            date_explicit=bool(_DATE_HINTS.search(create_text)),
            raw=text,
        )

    # Fallback to AI parsing only when regex/rules did not yield an actionable entry.
    ai = await ai_service.parse_with_ai(text)
    if ai is None:
        logger.info("parser_failed", message=text)
        return None

    op = _operation_from_ai(
        ai,
        text,
        expense_date=expense_date,
        date_explicit=bool(_DATE_HINTS.search(text)),
    )
    if op.action != "create":
        return op
    if op.amount is None or op.amount <= 0 or not op.merchant:
        logger.info("parser_failed", message=text)
        return None

    op.wallet = wallet
    op.category = ai.category or resolver.categorize(ai.merchant) or DEFAULT_CATEGORY
    return op


async def parse_expense(message: str, session: AsyncSession) -> ParsedOperation | None:
    """Compatibilidade: retorna apenas lançamentos novos (action="create")."""
    op = await parse_message(message, session)
    if op is None or op.action != "create":
        return None
    return op
