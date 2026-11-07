"""Send a DegreeWorks PDF to the backend and reload the stored audit."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid

from streamlit.runtime import exists, get_instance
from streamlit.runtime.scriptrunner_utils.script_run_context import (
    get_script_run_ctx,
)


class AuditUnavailable(Exception):
    """The backend could not be reached or rejected the upload."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def post_audit(
    base_url: str,
    pdf: bytes,
    filename: str,
    session_id: str | None = None,
) -> dict:
    """Parse and store an audit. Reuse session_id when the page already has one."""
    boundary = uuid.uuid4().hex
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "") or "audit.pdf"
    chunks = []
    if session_id:
        chunks.append(
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="session_id"\r\n\r\n'
                f"{session_id}\r\n"
            ).encode()
        )
    chunks.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
    )
    chunks.append(pdf)
    chunks.append(f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/audit",
        data=b"".join(chunks),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return _read(request)


def delete_audit(base_url: str, session_id: str) -> None:
    """Delete the stored audit. A missing key is success."""
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/audit/{session_id}",
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return
        raise AuditUnavailable(str(exc.reason), status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise AuditUnavailable(str(exc.reason)) from exc


def load_audit(base_url: str, session_id: str) -> dict | None:
    """Return the stored audit, or None when this session has expired."""
    request = urllib.request.Request(f"{base_url.rstrip('/')}/audit/{session_id}")
    try:
        return _read(request)
    except AuditUnavailable as exc:
        if getattr(exc, "status", None) == 404:
            return None
        raise


# Streamlit websocket session id -> (backend url, audit session id).
_BOUND: dict[str, tuple[str, str]] = {}


def watch_session(base_url: str, audit_session_id: str) -> None:
    """Delete this audit when the current Streamlit session disconnects."""
    if not exists():
        return
    context = get_script_run_ctx()
    if context is None:
        return
    _BOUND[context.session_id] = (base_url, audit_session_id)
    _install(get_instance())


def _install(runtime) -> None:
    if getattr(_install, "done", False):
        return
    original_disconnect = runtime.disconnect_session
    original_close = runtime.close_session

    def disconnect_session(session_id, *, client=None):
        try:
            _drop(session_id)
        finally:
            original_disconnect(session_id, client=client)

    def close_session(session_id):
        try:
            _drop(session_id)
        finally:
            original_close(session_id)

    runtime.disconnect_session = disconnect_session
    runtime.close_session = close_session
    _install.done = True


def _drop(streamlit_session_id: str) -> None:
    bound = _BOUND.pop(streamlit_session_id, None)
    if bound is None:
        return
    base_url, audit_session_id = bound
    try:
        delete_audit(base_url, audit_session_id)
    except AuditUnavailable:
        return


def _read(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise AuditUnavailable(str(exc.reason), status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise AuditUnavailable(str(exc.reason)) from exc
