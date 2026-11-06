"""Ask the backend for a retrieved syllabus reply."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class ChatFailed(Exception):
    """The chat route refused the question or could not be reached."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def post_chat(
    base_url: str,
    session_id: str,
    message: str,
    history: list[dict],
    prefs: dict,
) -> dict:
    """POST one question. Raises ChatFailed on HTTP errors and timeouts."""
    payload = json.dumps(
        {
            "session_id": session_id,
            "message": message,
            "history": history[-8:],
            "prefs": prefs,
        }
    ).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except TimeoutError as exc:
        raise ChatFailed("timed out") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.reason
        try:
            body = json.loads(exc.read().decode())
            if isinstance(body, dict) and body.get("detail"):
                detail = body["detail"]
        except (json.JSONDecodeError, UnicodeError):
            pass
        raise ChatFailed(str(detail), status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise ChatFailed(str(exc.reason)) from exc
