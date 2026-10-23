"""Build and configure the python-telegram-bot Application."""

from __future__ import annotations

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.bot import handlers
from app.config import settings


def build_application(*, polling: bool = False) -> Application:
    builder = ApplicationBuilder().token(settings.telegram_bot_token)
    if not polling:
        builder = builder.updater(None)  # webhook mode; no polling updater
    app: Application = builder.build()

    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("today", handlers.cmd_today))
    app.add_handler(CommandHandler("month", handlers.cmd_month))
    app.add_handler(CommandHandler("export", handlers.cmd_export))
    app.add_handler(CommandHandler("dashboard", handlers.cmd_dashboard))
    app.add_handler(CommandHandler("saldo", handlers.cmd_saldo))
    app.add_handler(CommandHandler("desfazer", handlers.cmd_undo))
    app.add_handler(CommandHandler(["remover", "apagar"], handlers.cmd_remove))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_message)
    )
    app.add_handler(MessageHandler(filters.VOICE, handlers.on_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.on_photo))
    app.add_error_handler(handlers.on_error)

    return app
