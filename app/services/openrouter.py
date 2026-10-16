"""OpenRouter client used as an AI fallback for hard-to-parse messages."""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL_CHAIN: list[str] = [
    "deepseek/deepseek-chat",
    "mistralai/mistral-7b-instruct",
    "qwen/qwen-2.5-7b-instruct",
]

SYSTEM_PROMPT = (
    "You are an expense parser. Extract the structured data from the user's message. "
    "Respond with strict JSON only and no commentary, matching this schema: "
    '{"merchant": string, "amount": number, "category": string, "notes": string}. '
    "Choose `category` from: Food, Transport, Shopping, Fuel, Bills, Entertainment, "
    "Health, Groceries, Travel, Other. If the message has no clear amount, set amount to 0."
)


@dataclass(slots=True)
class AIParseResult:
    merchant: str
    amount: float
    category: str
    notes: str


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter cannot be reached or returns invalid output."""


async def parse_with_ai(message: str, *, timeout: float = 6.0) -> AIParseResult | None:
    """Call OpenRouter with model fallback. Returns None on total failure."""

    if not settings.openrouter_api_key:
        logger.debug("openrouter_skipped_no_key")
        return None

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.app_url,
        "X-Title": "Finza",
    }

    payload_template = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        for model in MODEL_CHAIN:
            payload = {**payload_template, "model": model}
            try:
                resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = _coerce(content)
                if parsed is not None:
                    logger.info("openrouter_parsed", model=model)
                    return parsed
            except (httpx.HTTPError, KeyError, ValueError) as e:
                logger.warning("openrouter_model_failed", model=model, error=str(e))
                continue

    return None


def _coerce(content: str) -> AIParseResult | None:
    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        # Sometimes models wrap JSON in code fences; strip and retry once.
        cleaned = content.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

    if not isinstance(obj, dict):
        return None

    try:
        amount = float(obj.get("amount", 0) or 0)
    except (TypeError, ValueError):
        amount = 0.0

    return AIParseResult(
        merchant=str(obj.get("merchant", "")).strip()[:255],
        amount=amount,
        category=str(obj.get("category", "Other")).strip()[:64] or "Other",
        notes=str(obj.get("notes", "")).strip()[:500],
    )
