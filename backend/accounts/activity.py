"""Per-user activity log (sign-ins, uploads, searches, questions)."""

from __future__ import annotations

from fastapi import Request
from psycopg.types.json import Jsonb


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return (request.headers.get("user-agent") or "")[:300] or None


def log_event(conn, user_id, event: str, detail: dict | None = None, request: Request | None = None) -> None:
    conn.execute(
        """
        INSERT INTO activity_log (user_id, event, detail, ip, user_agent)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, event, Jsonb(detail or {}), client_ip(request), user_agent(request)),
    )
