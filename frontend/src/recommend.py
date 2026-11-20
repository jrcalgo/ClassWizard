"""Ask the backend for ranked courses (/recommend) and cited answers (/explain)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class BackendFailed(Exception):
    """The route refused the request or could not be reached.

    `body` keeps the parsed error body: /explain returns its evidence there
    when the language model is down, so the page can still show the facts.
    """

    def __init__(self, message: str, status: int | None = None, body: dict | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body or {}


def post_recommend(base_url: str, session_id: str, soc_codes: list[str], limit: int = 10) -> dict:
    """Ranked still-needed courses for the chosen careers. Usually under a second."""
    return _post(
        base_url,
        "/recommend",
        {"session_id": session_id, "soc_codes": soc_codes, "limit": limit},
        timeout=30,
    )


def post_explain(base_url: str, session_id: str, soc_codes: list[str], question: str) -> dict:
    """A cited answer from the local model. Seconds on a GPU, up to minutes on CPU.

    Waits longer than the backend's EXPLAIN_TIMEOUT (default 180 s) so the
    backend's 503 with fallback evidence arrives before this side gives up.
    """
    return _post(
        base_url,
        "/explain",
        {"session_id": session_id, "soc_codes": soc_codes, "question": question},
        timeout=240,
    )


def _post(base_url: str, path: str, payload: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except TimeoutError as exc:
        raise BackendFailed("timed out") from exc
    except urllib.error.HTTPError as exc:
        body: dict = {}
        detail = exc.reason
        try:
            parsed = json.loads(exc.read().decode())
            if isinstance(parsed, dict):
                body = parsed
                detail = parsed.get("detail") or detail
        except (json.JSONDecodeError, UnicodeError):
            pass
        raise BackendFailed(str(detail), status=exc.code, body=body) from exc
    except urllib.error.URLError as exc:
        raise BackendFailed(str(exc.reason)) from exc
