"""Redis session cache for a parsed DegreeWorks audit."""

from __future__ import annotations

import json
import os

import redis

# Crash backstop only. A live page renews this, and a closed page deletes the key.
_DEFAULT_TTL = 60


def _client() -> redis.Redis:
    return redis.Redis.from_url(os.environ["REDIS_URL"])


def _ttl() -> int:
    raw = os.environ.get("AUDIT_TTL_SECONDS", str(_DEFAULT_TTL))
    try:
        seconds = int(raw)
    except ValueError:
        return _DEFAULT_TTL
    if seconds < 1:
        return _DEFAULT_TTL
    return seconds


def _key(session_id: str) -> str:
    return f"audit:{session_id}"


def ping() -> bool:
    """Return whether Redis answers."""
    return bool(_client().ping())


def save_audit(session_id: str, audit: dict) -> None:
    """Store one parsed audit and set the session TTL."""
    _client().set(_key(session_id), json.dumps(audit), ex=_ttl())


def delete_audit(session_id: str) -> None:
    """Remove the stored audit. Missing keys are ignored."""
    _client().delete(_key(session_id))


def load_audit(session_id: str) -> dict | None:
    """Return the stored audit and slide its TTL forward."""
    client = _client()
    key = _key(session_id)
    raw = client.get(key)
    if raw is None:
        return None
    client.expire(key, _ttl())
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)
