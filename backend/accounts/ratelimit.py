"""Fixed-window rate limits in Redis for login, signup and email-sending routes."""

from __future__ import annotations

import hashlib
import os

import redis


def _client() -> redis.Redis:
    return redis.Redis.from_url(os.environ["REDIS_URL"])


def allow(bucket: str, subject: str, limit: int, window_seconds: int) -> bool:
    """Count one attempt; False once `limit` attempts happened inside the window.

    Fails open: if Redis is down, sign-in keeps working.
    """
    key = "rl:%s:%s" % (bucket, hashlib.sha256(subject.lower().encode()).hexdigest()[:32])
    try:
        client = _client()
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
        return count <= limit
    except Exception:
        return True
