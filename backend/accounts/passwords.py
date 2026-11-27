"""Password hashing with stdlib scrypt (memory-hard; OWASP-recommended parameters).

Stored format: scrypt$<log2 N>$<r>$<p>$<salt b64>$<hash b64>. The parameters
travel with the hash, so they can be raised later; needs_rehash() reports
hashes made with older parameters.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_LOG_N = 15  # N = 2**15, r = 8, p = 3: about 32 MiB per hash (OWASP alternative profile)
_R = 8
_P = 3
_DKLEN = 32
MIN_LENGTH = 8
MAX_LENGTH = 256


def _derive(password: str, salt: bytes, log_n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**log_n,
        r=r,
        p=p,
        maxmem=256 * 1024 * 1024,
        dklen=_DKLEN,
    )


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, _LOG_N, _R, _P)
    return f"scrypt${_LOG_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, log_n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _derive(password, _unb64(salt), int(log_n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, _unb64(digest))


def needs_rehash(stored: str) -> bool:
    return not stored.startswith(f"scrypt${_LOG_N}${_R}${_P}$")


def password_problem(password: str) -> str | None:
    """A user-facing reason the password is not acceptable, or None."""
    if len(password) < MIN_LENGTH:
        return f"Password must be at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"Password must be at most {MAX_LENGTH} characters."
    if password.strip() == "":
        return "Password cannot be blank."
    return None
