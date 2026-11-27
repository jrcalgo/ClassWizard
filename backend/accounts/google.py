"""Sign in with Google (OpenID Connect authorization-code flow).

The ID token is not needed: the code is exchanged server-to-server over TLS
with the client secret, and the profile comes from Google's userinfo endpoint
using the resulting access token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from urllib.parse import urlencode

import httpx

from backend.accounts.settings import google_client, public_base_url, session_secret

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def redirect_uri() -> str:
    return f"{public_base_url()}/api/auth/google/callback"


def new_state() -> tuple[str, str]:
    """(state for Google, signed cookie value that proves we issued it)."""
    state = secrets.token_urlsafe(24)
    signature = hmac.new(session_secret(), state.encode(), hashlib.sha256).hexdigest()
    return state, f"{state}.{signature}"


def state_matches(state: str | None, cookie: str | None) -> bool:
    if not state or not cookie or "." not in cookie:
        return False
    cookie_state, signature = cookie.rsplit(".", 1)
    expected = hmac.new(session_secret(), cookie_state.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected) and hmac.compare_digest(cookie_state, state)


def authorization_url(state: str) -> str:
    client = google_client()
    if client is None:
        raise RuntimeError("Google sign-in is not configured")
    query = {
        "client_id": client[0],
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def fetch_profile(code: str) -> dict:
    """Exchange the code and return {sub, email, email_verified, name}."""
    client = google_client()
    if client is None:
        raise RuntimeError("Google sign-in is not configured")
    with httpx.Client(timeout=10) as http:
        token = http.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": client[0],
                "client_secret": client[1],
                "redirect_uri": redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        token.raise_for_status()
        access_token = token.json()["access_token"]
        info = http.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        info.raise_for_status()
        profile = info.json()
    if not profile.get("sub") or not profile.get("email"):
        raise RuntimeError("Google did not return an account id and email")
    return profile
