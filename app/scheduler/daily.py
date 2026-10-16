"""Daily 9 PM summary scheduler."""

from __future__ import annotations

from io import BytesIO
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from app.config import settings
from app.db import repository as repo
from app.db.session import AsyncSessionLocal
from app.services import report as report_service
from app.utils.logging import get_logger
from app.utils.money import format_brl

logger = get_logger(__name__)


async def send_daily_reports(application: Application) -> None:
    """Build and send today's summary + PDF to every user with activity today."""
    today = report_service.today_in_tz()
    logger.info("daily_job_start", date=today.isoformat())

    async with AsyncSessionLocal() as session:
        users = await repo.list_users_with_today_expenses(session, today)

        for user in users:
            try:
                summary = await report_service.build_today_summary(session, user)
                if not summary.expenses:
                    continue

                text = report_service.format_telegram_summary(
                    summary, header="Gastos de hoje"
                )
                await application.bot.send_message(
                    chat_id=user.telegram_id, text=text
                )

                pdf_bytes = report_service.build_pdf(
                    summary,
                    owner_label=user.first_name or user.username,
                )
                bio = BytesIO(pdf_bytes)
                bio.name = f"daily-{today.isoformat()}.pdf"
                await application.bot.send_document(
                    chat_id=user.telegram_id,
                    document=bio,
                    filename=bio.name,
                    caption=f"Resumo do dia · Total {format_brl(summary.total)}",
                )

                await repo.upsert_daily_report(
                    session,
                    user_id=user.id,
                    report_date=today,
                    total_amount=summary.total,
                    pdf_path=None,
                )
                logger.info(
                    "daily_report_sent",
                    user_id=str(user.id),
                    total=str(summary.total),
                )
            except Exception as e:
                logger.exception(
                    "daily_report_failed",
                    user_id=str(user.id),
                    error=str(e),
                )

    logger.info("daily_job_done", users=len(users))


def build_scheduler(application: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.app_tz))
    scheduler.add_job(
        send_daily_reports,
        CronTrigger(hour=21, minute=0, timezone=ZoneInfo(settings.app_tz)),
        kwargs={"application": application},
        id="daily_reports",
        replace_existing=True,
        misfire_grace_time=600,
    )
    return scheduler
