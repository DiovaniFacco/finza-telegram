"""Magic-link JWT minting + signed session cookie helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote

import jwt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

JWT_ALGO = "HS256"
SESSION_COOKIE_NAME = "expense_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days


@dataclass(slots=True)
class CurrentUser:
    user_id: uuid.UUID
    telegram_id: int


def mint_magic_token(*, user_id: uuid.UUID, telegram_id: int, ttl_minutes: int = 15) -> str:
    """Sign a short-lived JWT used in the dashboard magic link."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tg": telegram_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        "kind": "magic",
    }
    raw = jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGO)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return raw


def magic_link_url(token: str) -> str:
    """Build a safe magic-link URL (JWT must be query-encoded)."""
    encoded = quote(token, safe="")
    return f"{settings.app_url.rstrip('/')}/auth?token={encoded}"


def normalize_magic_token(raw: str | None) -> str | None:
    """Repair tokens mangled by query parsers (e.g. '+' → space)."""
    if not raw:
        return None
    token = unquote(raw.strip())
    if " " in token and token.count(".") >= 2:
        token = token.replace(" ", "+")
    return token


def verify_magic_token(token: str | None) -> CurrentUser | None:
    token = normalize_magic_token(token)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        return None
    if payload.get("kind") != "magic":
        return None
    try:
        return CurrentUser(
            user_id=uuid.UUID(payload["sub"]),
            telegram_id=int(payload["tg"]),
        )
    except (KeyError, ValueError):
        return None


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="expense-session")


def make_session_cookie(*, user_id: uuid.UUID, telegram_id: int) -> str:
    """Create a signed, time-bound session cookie value."""
    return _serializer().dumps({"sub": str(user_id), "tg": telegram_id})


def read_session_cookie(value: str | None) -> CurrentUser | None:
    if not value:
        return None
    try:
        data = _serializer().loads(value, max_age=SESSION_MAX_AGE_SECONDS)
    except (SignatureExpired, BadSignature):
        return None
    try:
        return CurrentUser(
            user_id=uuid.UUID(data["sub"]),
            telegram_id=int(data["tg"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


def apply_session_cookie(response, request, *, user_id: uuid.UUID, telegram_id: int):
    """Set the session cookie with correct flags behind Railway/nginx."""
    from app.utils.request import is_https

    cookie_value = make_session_cookie(user_id=user_id, telegram_id=telegram_id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=is_https(request),
        path="/",
    )


def clear_session_cookie(response, request):
    from app.utils.request import is_https

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=is_https(request),
    )
