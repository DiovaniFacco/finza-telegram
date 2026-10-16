"""FastAPI entrypoint with PTB application + APScheduler lifecycle."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import __version__
from app.bot.application import build_application
from app.config import settings
from app.routes import auth as auth_routes
from app.routes import dashboard as dashboard_routes
from app.routes import webhook as webhook_routes
from app.scheduler.daily import build_scheduler
from app.utils.logging import configure_logging, get_logger
from app.db.session import check_database
from app.utils.migrate import run_migrations

configure_logging()
logger = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


async def _register_telegram_webhook(bot_app) -> None:
    """Point Telegram at this deployment's public webhook URL."""
    if not settings.app_url.startswith("https://"):
        logger.error(
            "webhook_requires_https",
            app_url=settings.app_url,
            hint="Set APP_URL to your Railway https URL, or deploy on Railway (auto-detected).",
        )
        return

    try:
        await bot_app.bot.delete_webhook(drop_pending_updates=False)
        ok = await bot_app.bot.set_webhook(
            url=settings.webhook_url,
            allowed_updates=["message", "edited_message", "callback_query"],
            drop_pending_updates=False,
        )
        info = await bot_app.bot.get_webhook_info()
        logger.info(
            "webhook_registered",
            ok=ok,
            url=settings.webhook_url,
            telegram_url=info.url,
            pending=info.pending_update_count,
        )
        if info.url != settings.webhook_url:
            logger.error(
                "webhook_mismatch",
                expected=settings.webhook_url,
                actual=info.url,
            )
    except Exception as e:
        logger.exception("webhook_registration_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    try:
        await check_database()
        logger.info("database_connected")
    except Exception as e:
        logger.exception("database_connection_failed", error=str(e))

    bot_app = build_application()
    await bot_app.initialize()
    await bot_app.start()
    app.state.bot_application = bot_app

    logger.info(
        "app_startup",
        app_url=settings.app_url,
        webhook_url=settings.webhook_url,
        version=__version__,
    )

    await _register_telegram_webhook(bot_app)

    scheduler = build_scheduler(bot_app)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("scheduler_started", tz=settings.app_tz)

    try:
        yield
    finally:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        try:
            await bot_app.stop()
        except Exception:
            pass
        try:
            await bot_app.shutdown()
        except Exception:
            pass
        logger.info("shutdown_complete")


app = FastAPI(
    title="Finza",
    version=__version__,
    lifespan=lifespan,
)

# Railway/nginx terminate TLS; trust X-Forwarded-Proto for cookies and URLs.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(url="/login", status_code=303)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_error", path=request.url.path, error=str(exc))
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(url="/login", status_code=303)
    return JSONResponse({"detail": "internal_server_error"}, status_code=500)

app.include_router(webhook_routes.router)
app.include_router(auth_routes.router)
app.include_router(dashboard_routes.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Use this to confirm Railway is running THIS app (not another project)."""
    return {
        "status": "ok",
        "app": "finza",
        "version": __version__,
        "webhook_path": settings.webhook_path,
    }


@app.get("/api/db-check")
async def db_check():
    """Debug: verify database connectivity from Railway."""
    try:
        await check_database()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}


@app.get("/api/webhook-info")
async def webhook_info(request: Request):
    """Debug: where Telegram is currently sending updates."""
    bot_app = getattr(request.app.state, "bot_application", None)
    if bot_app is None:
        return {"error": "bot not ready"}
    info = await bot_app.bot.get_webhook_info()
    return {
        "expected_url": settings.webhook_url,
        "telegram_url": info.url,
        "pending_updates": info.pending_update_count,
        "last_error_date": info.last_error_date,
        "last_error_message": info.last_error_message,
        "app_url": settings.app_url,
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
