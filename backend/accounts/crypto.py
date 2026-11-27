"""Encryption at rest for saved audits.

AUDIT_ENCRYPTION_KEY holds one or more comma-separated Fernet keys. The first
encrypts; all of them decrypt, so a key can be rotated by putting the new one
first. Without a valid key, audits are simply not saved for signed-in users.
"""

from __future__ import annotations

import json
import os
import sys

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

_cache: tuple[str, MultiFernet | None] | None = None


def _fernet() -> MultiFernet | None:
    global _cache
    raw = os.environ.get("AUDIT_ENCRYPTION_KEY", "")
    if _cache is not None and _cache[0] == raw:
        return _cache[1]
    keys = [part.strip() for part in raw.split(",") if part.strip()]
    fernet: MultiFernet | None = None
    if keys:
        try:
            fernet = MultiFernet([Fernet(key.encode()) for key in keys])
        except (ValueError, TypeError):
            print("AUDIT_ENCRYPTION_KEY is invalid; saved audits are disabled.", file=sys.stderr)
    _cache = (raw, fernet)
    return fernet


def enabled() -> bool:
    return _fernet() is not None


def encrypt_json(value) -> bytes:
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError("audit encryption is not configured")
    return fernet.encrypt(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def decrypt_json(token: bytes):
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError("audit encryption is not configured")
    try:
        return json.loads(fernet.decrypt(bytes(token)).decode("utf-8"))
    except InvalidToken as exc:
        raise RuntimeError("saved audit could not be decrypted") from exc
