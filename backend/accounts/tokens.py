"""Single-use email tokens for address verification and password reset."""

from __future__ import annotations

import secrets
from datetime import timedelta

from backend.accounts.sessions import hash_token

TTL = {"verify": timedelta(hours=48), "reset": timedelta(hours=1)}


def issue(conn, user_id, purpose: str) -> str:
    """Create a token; earlier unused tokens of the same purpose stop working."""
    token = secrets.token_urlsafe(32)
    conn.execute(
        "UPDATE email_tokens SET used_at = now() WHERE user_id = %s AND purpose = %s AND used_at IS NULL",
        (user_id, purpose),
    )
    conn.execute(
        """
        INSERT INTO email_tokens (token_hash, user_id, purpose, expires_at)
        VALUES (%s, %s, %s, now() + %s)
        """,
        (hash_token(token), user_id, purpose, TTL[purpose]),
    )
    return token


def consume(conn, token: str, purpose: str):
    """Mark the token used and return its user id, or None if invalid, expired or used."""
    if not token or len(token) > 200:
        return None
    row = conn.execute(
        """
        UPDATE email_tokens SET used_at = now()
        WHERE token_hash = %s AND purpose = %s AND used_at IS NULL AND expires_at > now()
        RETURNING user_id
        """,
        (hash_token(token), purpose),
    ).fetchone()
    return row["user_id"] if row else None
