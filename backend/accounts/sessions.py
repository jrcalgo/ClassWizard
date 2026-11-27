"""Cookie sessions: a random token in an httpOnly cookie, its SHA-256 in Postgres."""

from __future__ import annotations

import hashlib
import secrets
import sys
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response

from backend.accounts import db
from backend.accounts.activity import client_ip, user_agent
from backend.accounts.settings import SESSION_COOKIE, SESSION_DAYS, secure_cookies

_SLIDE_AFTER = timedelta(hours=1)

USER_COLUMNS = (
    "u.id, u.email, u.display_name, u.email_verified_at, u.created_at, "
    "u.password_hash IS NOT NULL AS has_password, u.google_sub IS NOT NULL AS google_linked"
)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def public_user(row: dict) -> dict:
    """The user fields the frontend may see."""
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "display_name": row.get("display_name"),
        "email_verified": row.get("email_verified_at") is not None,
        "has_password": bool(row.get("has_password")),
        "google_linked": bool(row.get("google_linked")),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def create_session(conn, user_id, request: Request | None) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO user_sessions (user_id, token_hash, expires_at, ip, user_agent)
        VALUES (%s, %s, now() + make_interval(days => %s), %s, %s)
        """,
        (user_id, hash_token(token), SESSION_DAYS, client_ip(request), user_agent(request)),
    )
    conn.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user_id,))
    return token


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path="/",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=secure_cookies())


def lookup(conn, token: str) -> dict | None:
    row = conn.execute(
        f"""
        SELECT {USER_COLUMNS}, s.id AS session_row, s.last_seen_at, s.expires_at
        FROM user_sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = %s AND s.expires_at > now()
        """,
        (hash_token(token),),
    ).fetchone()
    if row is None:
        return None
    # Sliding expiry, written at most once an hour per session.
    conn.execute(
        """
        UPDATE user_sessions
        SET last_seen_at = now(), expires_at = now() + make_interval(days => %s)
        WHERE id = %s AND last_seen_at < now() - %s
        """,
        (SESSION_DAYS, row["session_row"], _SLIDE_AFTER),
    )
    return row


def revoke(conn, token: str) -> None:
    conn.execute("DELETE FROM user_sessions WHERE token_hash = %s", (hash_token(token),))


def revoke_all(conn, user_id, keep_token: str | None = None) -> None:
    if keep_token:
        conn.execute(
            "DELETE FROM user_sessions WHERE user_id = %s AND token_hash <> %s",
            (user_id, hash_token(keep_token)),
        )
    else:
        conn.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))


def current_user_optional(request: Request) -> dict | None:
    """The signed-in user's row, or None. Never fails the request: a database
    error degrades to anonymous so the core planning flow keeps working."""
    if hasattr(request.state, "cw_user"):
        return request.state.cw_user
    user = None
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            with db.connect() as conn:
                user = lookup(conn, token)
        except Exception as exc:
            print(f"session lookup failed: {exc!r}", file=sys.stderr)
            user = None
    request.state.cw_user = user
    return user


def require_user(user: dict | None = Depends(current_user_optional)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="sign in required")
    return user
