"""Reject cross-site state-changing requests.

The session cookie is SameSite=Lax, which already stops most cross-site POSTs;
this checks the Origin (or Referer) header as a second layer. A request passes
when its origin is the site it was sent to (same host as the Host header that
nginx forwards), PUBLIC_BASE_URL, or one of ALLOWED_ORIGINS. Requests with
neither header (server-side clients, tests) are not browser-originated and pass.
"""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.accounts.settings import allowed_origins

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _parts(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    return parsed.scheme.lower(), parsed.netloc.lower()


def origin_allowed(origin: str, host: str | None) -> bool:
    if not origin or origin.lower() == "null":
        return False
    scheme, netloc = _parts(origin)
    if not scheme or not netloc:
        return False
    if host and netloc == host.lower():
        return True  # same-origin: the page and the API are served together
    return f"{scheme}://{netloc}" in allowed_origins()


class OriginCheckMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _UNSAFE:
            origin = request.headers.get("origin")
            if origin is None:
                referer = request.headers.get("referer")
                if referer:
                    scheme, netloc = _parts(referer)
                    origin = f"{scheme}://{netloc}"
            host = request.headers.get("x-forwarded-host") or request.headers.get("host")
            if origin is not None and not origin_allowed(origin, host):
                return JSONResponse({"detail": "cross-site request refused"}, status_code=403)
        return await call_next(request)
