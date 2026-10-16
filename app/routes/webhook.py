"""FastAPI route that forwards Telegram updates to python-telegram-bot."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from telegram import Update

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != settings.webhook_secret:
        logger.warning("webhook_rejected_bad_secret", path_secret=secret[:8] + "...")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad secret")

    application = request.app.state.bot_application
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="bot not ready",
        )

    data = await request.json()
    update = Update.de_json(data, application.bot)
    update_id = data.get("update_id")
    message = data.get("message") or data.get("edited_message") or {}
    text_preview = (message.get("text") or "")[:80]
    logger.info("webhook_received", update_id=update_id, text=text_preview)

    await application.process_update(update)
    return {"ok": True}
