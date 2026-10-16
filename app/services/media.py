"""Mídia 100% gratuita via Groq: voz (Whisper) + foto de comprovante (visão).

Usa GROQ_API_KEY do .env. Sem cartão, sem recarga.
"""

from __future__ import annotations

import base64
import io
import json
import os
import tempfile

from app.utils.logging import get_logger

logger = get_logger(__name__)

WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")

VISION_PROMPT = (
    "Você extrai dados de comprovantes/notas fiscais em português. "
    "Analise a imagem e responda APENAS com JSON válido, sem comentários: "
    '{"amount": number, "category": string, "description": string, "kind": "expense"}. '
    "amount = valor total pago. category dentre: Alimentação, Transporte, Moradia, "
    "Saúde, Lazer, Educação, Compras, Contas, Salário, Freelance, Investimento, Outros. "
    "description = nome do estabelecimento ou resumo (ex: 'Mercado Extra'). "
    "Se não for comprovante ou não der pra ler valor, use amount 0 e category Outros."
)


def _groq_client():
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY não configurada")
    return Groq(api_key=api_key)


def transcribe_ogg(ogg_bytes: bytes) -> str:
    """Transcreve áudio ogg/opus (voz do Telegram) via Whisper Groq."""
    client = _groq_client()
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(ogg_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            t = client.audio.transcriptions.create(
                model=WHISPER_MODEL, file=f, language="pt")
        text = t.text.strip()
        logger.info("voice_transcribed", text=text[:120])
        return text
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def extract_receipt(image_bytes: bytes, mime: str = "image/jpeg") -> dict:
    """Extrai {amount, category, description, kind} de foto de comprovante."""
    client = _groq_client()
    b64 = base64.b64encode(image_bytes).decode()
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
    )
    raw = (resp.choices[0].message.content or "").strip()
    logger.info("receipt_raw", raw=raw[:200])
    data = _json_first(raw)
    return {
        "amount": float(data.get("amount", 0) or 0),
        "category": str(data.get("category", "Outros")).strip() or "Outros",
        "description": str(data.get("description", "")).strip()[:255],
        "kind": "income" if str(data.get("kind", "")).lower() == "income" else "expense",
    }


def _json_first(text: str) -> dict:
    import re as _re

    cands = [text]
    cleaned = text.strip().strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    cands.append(cleaned)
    m = _re.search(r"\{.*\}", text, _re.DOTALL)
    if m:
        cands.append(m.group(0))
    for cand in cands:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return {}


async def telegram_file_bytes(file_obj) -> bytes:
    """Baixa arquivo do Telegram para bytes (voz ou foto)."""
    buf = io.BytesIO()
    await file_obj.download_to_memory(buf)
    return buf.getvalue()
