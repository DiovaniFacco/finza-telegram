"""HTTP request helpers for reverse-proxy deployments (Railway, etc.)."""

from __future__ import annotations

from starlette.requests import Request


def is_https(request: Request) -> bool:
    """True when the client used HTTPS (respects X-Forwarded-Proto)."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if forwarded == "https":
        return True
    return request.url.scheme == "https"
