"""Dev local sem HTTPS/túnel: bot em polling + dashboard + scheduler.

Uso: /tmp/finza-tg-venv/bin/python run_polling.py
"""

from __future__ import annotations

import asyncio

from app.bot.application import build_application
from app.config import settings
from app.db.session import check_database
from app.scheduler.daily import build_scheduler
from app.utils.logging import configure_logging, get_logger
from app.utils.migrate import run_migrations

configure_logging()
logger = get_logger(__name__)


async def main() -> None:
    run_migrations()
    await check_database()
    logger.info("database_connected")

    bot_app = build_application(polling=True)
    await bot_app.initialize()
    await bot_app.start()

    scheduler = build_scheduler(bot_app)
    scheduler.start()
    logger.info("polling_started", tz=settings.app_tz)

    try:
        await bot_app.updater.start_polling(drop_pending_updates=False)  # type: ignore[union-attr]
        # Roda até Ctrl+C
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            await bot_app.updater.stop()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        await bot_app.stop()
        await bot_app.shutdown()
        logger.info("shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
