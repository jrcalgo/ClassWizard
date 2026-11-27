"""Environment-driven settings for accounts. Read at call time so tests can monkeypatch."""

from __future__ import annotations

import os
import secrets
import sys
from functools import lru_cache
from urllib.parse import urlparse

SESSION_COOKIE = "cw_session"
OAUTH_COOKIE = "cw_oauth"
SESSION_DAYS = 30


def public_base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "http://localhost:8501").rstrip("/")


def secure_cookies() -> bool:
    return urlparse(public_base_url()).scheme == "https"


def allowed_origins() -> set[str]:
    """Origins allowed to send state-changing requests (CSRF check)."""
    origins = {_origin(public_base_url())}
    for extra in os.environ.get("ALLOWED_ORIGINS", "").split(","):
        if extra.strip():
            origins.add(_origin(extra.strip()))
    return origins


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}".lower()


@lru_cache(maxsize=1)
def session_secret() -> bytes:
    """Key for signing the short-lived OAuth state cookie."""
    value = os.environ.get("SESSION_SECRET", "")
    if value:
        return value.encode()
    print(
        "SESSION_SECRET is not set; using a random per-process key (Google sign-in "
        "state will not survive a restart).",
        file=sys.stderr,
    )
    return secrets.token_bytes(32)


def google_client() -> tuple[str, str] | None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        return client_id, client_secret
    return None


def chat_mode() -> str:
    mode = os.environ.get("CHAT_MODE", "explain").strip().lower()
    return mode if mode in {"explain", "chat"} else "explain"
