"""Magic-link auth routes: verify JWT, set session cookie, redirect to dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import repository as repo
from app.db.session import get_session
from app.services import auth as auth_service
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/auth")
async def auth_with_token(
    request: Request,
    token: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    try:
        if not token:
            return HTMLResponse(_missing_token_page(), status_code=400)

        current = auth_service.verify_magic_token(token)
        if current is None:
            logger.warning("auth_magic_token_invalid")
            return HTMLResponse(_expired_token_page(), status_code=401)

        user = await repo.get_user(session, current.user_id)
        if user is None:
            logger.warning("auth_user_not_found", user_id=str(current.user_id))
            return HTMLResponse(_expired_token_page(), status_code=401)

        response = RedirectResponse(url="/", status_code=303)
        auth_service.apply_session_cookie(
            response,
            request,
            user_id=user.id,
            telegram_id=user.telegram_id,
        )
        logger.info("auth_success", user_id=str(user.id), telegram_id=user.telegram_id)
        return response
    except Exception:
        logger.exception("auth_failed")
        return _redirect_to_login()


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    auth_service.clear_session_cookie(response, request)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    return HTMLResponse(_login_page())


def _login_page() -> str:
    template = templates.env.get_template("landing.html")
    return template.render(
        bot_username=settings.telegram_bot_username.lstrip("@"),
        bot_url=settings.bot_url,
        github_url=settings.github_repo_url,
        app_url=settings.app_url,
    )


def _missing_token_page() -> str:
    return _notice_page(
        title="Link incomplete",
        heading="This link is incomplete",
        message="The magic link is missing its token. Send "
        "<code class='px-1.5 py-0.5 rounded bg-slate-100 dark:bg-white/10'>/dashboard</code> "
        "to the bot to get a fresh one.",
    )


def _redirect_to_login() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


def _expired_token_page() -> str:
    return _notice_page(
        title="Link expired",
        heading="This link has expired",
        message="Magic links are valid for 15 minutes. Send "
        "<code class='px-1.5 py-0.5 rounded bg-slate-100 dark:bg-white/10'>/dashboard</code> "
        "to the bot to get a new one.",
    )


def _notice_page(*, title: str, heading: str, message: str) -> str:
    """Small branded page for broken/expired magic links."""
    bot_username = settings.telegram_bot_username.lstrip("@")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} · Finza</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>tailwind.config = {{ darkMode: 'class' }};</script>
</head>
<body class="bg-slate-50 dark:bg-slate-950 min-h-screen flex items-center justify-center text-slate-900 dark:text-slate-100 p-4">
  <div class="max-w-md w-full p-8 rounded-2xl bg-white/70 dark:bg-white/5 backdrop-blur border border-white/40 dark:border-white/10 shadow-xl">
    <div class="flex items-center gap-2 mb-4">
      <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-pink-500 flex items-center justify-center text-white font-bold shadow-lg shadow-indigo-500/30">F</div>
      <span class="text-lg font-semibold tracking-tight">Finza</span>
    </div>
    <h1 class="text-2xl font-semibold mb-2">{heading}</h1>
    <p class="text-slate-600 dark:text-slate-400 mb-6">{message}</p>
    <a href="{settings.bot_url}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium text-white bg-gradient-to-br from-indigo-500 to-pink-500 shadow-lg shadow-indigo-500/30 hover:opacity-90 transition">
      Open @{bot_username} in Telegram
    </a>
    <p class="mt-6 text-sm text-slate-500 dark:text-slate-400">
      <a href="/login" class="underline hover:text-slate-700 dark:hover:text-slate-200">Back to home</a>
    </p>
  </div>
</body>
</html>"""

