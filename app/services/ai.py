"""IA gratuita em cadeia: Groq (primário, 1000 req/dia) → OpenRouter :free (fallback, 50 req/dia).

Mesma interface do antigo openrouter.py: `parse_with_ai(texto)` retorna
AIParseResult ou None. Categorias e prompts em PT-BR.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx

from app.utils.logging import get_logger

logger = get_logger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

GROQ_MODEL = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-20b")
OPENROUTER_FALLBACKS: list[str] = [
    m.strip()
    for m in os.getenv(
        "OPENROUTER_FALLBACK_MODELS",
        "google/gemma-4-26b-a4b-it:free,nvidia/nemotron-3.5-lightning:free",
    ).split(",")
    if m.strip()
]

SYSTEM_PROMPT = (
    "Você extrai dados financeiros de mensagens em português. "
    "Responda APENAS com JSON válido, sem comentários, neste esquema: "
    '{"merchant": string, "amount": number, "category": string, "notes": string, '
    '"kind": "income", "expense" ou "investment"}. '
    "Use kind=income para entradas (recebi, salário, freelance); "
    "kind=investment para aportes/investimentos (investi, aporte, tesouro, ações, CDB); "
    "senão kind=expense. "
    "Escolha `category` dentre: Alimentação, Transporte, Moradia, Saúde, Lazer, "
    "Educação, Compras, Contas, Salário, Freelance, Investimento, Outros. "
    "Se não houver valor claro, use amount 0. "
    'Exemplo: "gastei 45 no ifood" → '
    '{"merchant": "iFood", "amount": 45, "category": "Alimentação", "notes": "", "kind": "expense"}.'
)


@dataclass(slots=True)
class AIParseResult:
    merchant: str
    amount: float
    category: str
    notes: str
    kind: str = "expense"


class AIError(RuntimeError):
    """IA indisponível em todos os provedores."""


async def parse_with_ai(message: str, *, timeout: float = 20.0) -> AIParseResult | None:
    """Tenta Groq primeiro; cai para OpenRouter :free. None se tudo falhar."""
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        result = await _call_groq(groq_key, message, timeout=timeout)
        if result is not None:
            return result
        logger.warning("groq_failed_falling_back")

    or_key = os.getenv("OPENROUTER_API_KEY", "")
    if or_key:
        result = await _call_openrouter(or_key, message, timeout=timeout)
        if result is not None:
            return result

    logger.warning("ai_all_providers_failed")
    return None


async def _call_groq(api_key: str, message: str, *, timeout: float) -> AIParseResult | None:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "temperature": 0,
        "max_tokens": 300,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        parsed = _coerce(content)
        if parsed is not None:
            logger.info("groq_parsed", model=GROQ_MODEL)
        return parsed
    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.warning("groq_model_failed", model=GROQ_MODEL, error=str(e)[:200])
        return None


async def _call_openrouter(api_key: str, message: str, *, timeout: float) -> AIParseResult | None:
    from app.config import settings

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.app_url,
        "X-Title": "Finza Telegram",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        for model in OPENROUTER_FALLBACKS:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            }
            try:
                resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                parsed = _coerce(content)
                if parsed is not None:
                    logger.info("openrouter_parsed", model=model)
                    return parsed
            except (httpx.HTTPError, KeyError, ValueError) as e:
                logger.warning("openrouter_model_failed", model=model, error=str(e)[:200])
                continue
    return None


def _coerce(content: str) -> AIParseResult | None:
    import re as _re

    candidates = [content]
    cleaned = content.strip().strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    candidates.append(cleaned)
    # Extrai o primeiro bloco {...} (salva modelos verborrágicos)
    m = _re.search(r"\{.*\}", content, _re.DOTALL)
    if m:
        candidates.append(m.group(0))

    obj = None
    for cand in candidates:
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, dict):
                obj = parsed
                break
        except json.JSONDecodeError:
            continue
    if obj is None:
        return None

    try:
        amount = float(obj.get("amount", 0) or 0)
    except (TypeError, ValueError):
        amount = 0.0

    kind = str(obj.get("kind", "expense")).strip().lower()
    if kind not in ("income", "expense", "investment"):
        kind = "expense"
    return AIParseResult(
        merchant=str(obj.get("merchant", "")).strip()[:255],
        amount=amount,
        category=str(obj.get("category", "Outros")).strip()[:64] or "Outros",
        notes=str(obj.get("notes", "")).strip()[:500],
        kind=kind,
    )
