"""Telegram bot command + message handlers."""

from __future__ import annotations

from io import BytesIO

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import replies
from app.db import repository as repo
from app.db.session import AsyncSessionLocal
from app.services import auth as auth_service
from app.services import media as media_service
from app.services import operations as operations_service
from app.services import report as report_service
from app.services.parser import parse_message
from app.utils.logging import get_logger
from app.utils.money import format_brl

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# /start, /help
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    tg = update.effective_user
    async with AsyncSessionLocal() as session:
        await repo.upsert_user(
            session,
            telegram_id=tg.id,
            username=tg.username,
            first_name=tg.first_name,
        )
    await update.message.reply_text(
        replies.WELCOME.format(name=tg.first_name or "there")
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    await update.message.reply_text(
        replies.HELP.format(name=update.effective_user.first_name or "there")
    )


# ---------------------------------------------------------------------------
# /today, /month
# ---------------------------------------------------------------------------


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        summary = await report_service.build_today_summary(session, user)

    if not summary.expenses:
        await update.message.reply_text(replies.NO_TODAY)
        return

    text = report_service.format_telegram_summary(summary, header="Gastos de hoje")
    await update.message.reply_text(text)


async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        summary = await report_service.build_month_summary(session, user)

    if not summary.expenses:
        await update.message.reply_text(replies.NO_MONTH)
        return

    text = report_service.format_telegram_summary(
        summary, header=f"{summary.label} – Resumo"
    )
    await update.message.reply_text(text)


# ---------------------------------------------------------------------------
# /export – PDF
# ---------------------------------------------------------------------------


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        summary = await report_service.build_month_summary(session, user)

    pdf = report_service.build_pdf(
        summary,
        owner_label=update.effective_user.first_name or update.effective_user.username,
    )
    bio = BytesIO(pdf)
    bio.name = f"expenses-{summary.label.replace(' ', '-')}.pdf"
    await update.message.reply_document(
        document=bio,
        filename=bio.name,
        caption=f"{summary.label} — Total {format_brl(summary.total)}",
    )


# ---------------------------------------------------------------------------
# /dashboard – magic link
# ---------------------------------------------------------------------------


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )

    token = auth_service.mint_magic_token(
        user_id=user.id, telegram_id=user.telegram_id
    )
    url = auth_service.magic_link_url(token)
    await update.message.reply_text(replies.DASHBOARD_LINK.format(url=url))


# ---------------------------------------------------------------------------
# Free-text expense logging
# ---------------------------------------------------------------------------


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if not text or text.startswith("/"):
        return

    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        parsed = await parse_message(text, session)
        if parsed is None:
            await update.message.reply_text(replies.UNPARSEABLE)
            return

        result = await operations_service.execute(session, user, parsed)

    logger.info(
        "message_handled",
        telegram_id=update.effective_user.id,
        action=parsed.action,
        status=result.status,
        merchant=parsed.merchant,
        amount=str(parsed.amount) if parsed.amount is not None else None,
        category=parsed.category,
        kind=parsed.kind,
        wallet=parsed.wallet,
        wallet_to=parsed.wallet_to or None,
        source=parsed.source,
    )

    await update.message.reply_text(replies.format_operation_result(result))


# ---------------------------------------------------------------------------
# /saldo – saldos gerais + saldo inicial
# ---------------------------------------------------------------------------


async def cmd_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra saldos gerais. Uso: /saldo | /saldo conta 700 | /saldo dinheiro 150"""
    if not update.effective_user or not update.message:
        return
    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        args = (context.args or [])
        if len(args) >= 2 and args[0].lower() in ("conta", "dinheiro"):
            from decimal import Decimal, InvalidOperation

            try:
                value = Decimal(args[1].replace(".", "").replace(",", ".")) \
                    if "," in args[1] else Decimal(args[1])
            except (InvalidOperation, ValueError):
                await update.message.reply_text(
                    "Valor inválido 😅 Ex: `/saldo conta 700` ou `/saldo dinheiro 150,50`")
                return
            await repo.set_initial_balance(
                session, user_id=user.id, wallet=args[0].lower(), amount=value)
            await update.message.reply_text(
                f"✅ Saldo inicial da *{args[0].lower()}* definido: {format_brl(value)}")
            return

        balances = await repo.general_balances(session, user.id)

    await update.message.reply_text(
        "💳 *Saldos gerais* (acumulado, não zera no mês):\n\n"
        f"🏦 Conta: {format_brl(balances.get('conta', 0))}\n"
        f"💵 Dinheiro: {format_brl(balances.get('dinheiro', 0))}\n"
        f"📈 Investido (total): {format_brl(balances.get('investido', 0))}\n\n"
        "Pra definir saldo inicial: `/saldo conta 700` ou `/saldo dinheiro 150`"
    )


# ---------------------------------------------------------------------------
# /remover, /apagar – remove um lançamento (atalho para o texto livre)
# ---------------------------------------------------------------------------


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    args = " ".join(context.args or []).strip()
    if not args:
        await update.message.reply_text(
            "Uso: `/remover 500 dos investimentos` ou `/remover o último lançamento`."
        )
        return

    text = f"remover {args}"
    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        parsed = await parse_message(text, session)
        if parsed is None:
            await update.message.reply_text(replies.UNPARSEABLE)
            return
        result = await operations_service.execute(session, user, parsed)

    logger.info(
        "remove_command",
        telegram_id=update.effective_user.id,
        status=result.status,
        amount=str(parsed.amount) if parsed.amount is not None else None,
    )
    await update.message.reply_text(replies.format_operation_result(result))


# ---------------------------------------------------------------------------
# /desfazer – remove o último lançamento
# ---------------------------------------------------------------------------


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        result = await operations_service.undo_last(session, user)

    logger.info(
        "undo_last",
        telegram_id=update.effective_user.id,
        status=result.status,
        entries=len(result.entries),
    )
    await update.message.reply_text(replies.format_operation_result(result))


# ---------------------------------------------------------------------------
# Voice messages (áudio → transcreve → lança)
# ---------------------------------------------------------------------------


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.voice:
        return
    voice = update.message.voice
    if voice.file_size and voice.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("Áudio muito grande 😅 Manda um mais curto!")
        return

    await update.message.reply_text("🎙️ Ouvindo...")
    try:
        tg_file = await context.bot.get_file(voice.file_id)
        audio_bytes = await media_service.telegram_file_bytes(tg_file)
        text = media_service.transcribe_ogg(audio_bytes)
    except Exception:
        logger.exception("voice_transcribe_failed")
        await update.message.reply_text(
            "Não consegui entender o áudio 😅 Tente de novo ou mande por texto!"
        )
        return

    if not text:
        await update.message.reply_text(
            "Não consegui entender o áudio 😅 Tente de novo ou mande por texto!"
        )
        return

    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        parsed = await parse_message(text, session)
        if parsed is None:
            await update.message.reply_text(
                f'Ouvi: "{text}"\n\n{replies.UNPARSEABLE}'
            )
            return

        if parsed.notes:
            parsed.notes = f"{parsed.notes} · via áudio: {text[:180]}"
        else:
            parsed.notes = f"via áudio: {text[:200]}"

        result = await operations_service.execute(session, user, parsed)

    await update.message.reply_text(
        f'🎙️ Ouvi: "{text}"\n\n' + replies.format_operation_result(result)
    )


# ---------------------------------------------------------------------------
# Photos (comprovante → visão → lança)
# ---------------------------------------------------------------------------


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.photo:
        return
    photo = update.message.photo[-1]  # maior resolução
    if photo.file_size and photo.file_size > 15 * 1024 * 1024:
        await update.message.reply_text("Foto muito grande 😅 Tente uma menor!")
        return

    await update.message.reply_text("🧾 Lendo comprovante...")
    try:
        tg_file = await context.bot.get_file(photo.file_id)
        image_bytes = await media_service.telegram_file_bytes(tg_file)
        data = media_service.extract_receipt(image_bytes)
    except Exception:
        logger.exception("receipt_extract_failed")
        await update.message.reply_text(
            "Não consegui ler o comprovante 😅 Tente outra foto ou mande por texto!"
        )
        return

    if not data.get("amount"):
        await update.message.reply_text(
            "Não encontrei valor nesse comprovante 😅 Tente outra foto ou mande por texto!"
        )
        return

    caption = (update.message.caption or "").strip()
    merchant = data.get("description") or caption or "Comprovante"
    category = data.get("category") or "Outros"

    async with AsyncSessionLocal() as session:
        user = await repo.upsert_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        await repo.create_expense(
            session,
            user_id=user.id,
            merchant=merchant[:255].title(),
            amount=data["amount"],
            category=category,
            notes="via foto",
            expense_date=report_service.today_in_tz(),
            kind=data.get("kind", "expense"),
        )

    await update.message.reply_text(
        replies.LOGGED_EXPENSE.format(
            amount=format_brl(data["amount"]),
            merchant=merchant,
            category=category,
        )
    )


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("bot_error", error=str(context.error))
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Something went wrong on my side. Please try again."
            )
        except Exception:  # pragma: no cover - best effort
            pass
