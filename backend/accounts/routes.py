"""HTTP routes for accounts, saved state and runtime config.

nginx serves the frontend and proxies /api/* here with the /api prefix removed,
so these paths are what the backend sees.
"""

from __future__ import annotations

import re
import sys
import uuid
from datetime import datetime

import psycopg
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from backend.accounts import crypto, db, google, mailer, ratelimit, tokens
from backend.accounts.activity import client_ip, log_event
from backend.accounts.passwords import hash_password, needs_rehash, password_problem, verify_password
from backend.accounts.sessions import (
    USER_COLUMNS,
    clear_cookie,
    create_session,
    current_user_optional,
    public_user,
    require_user,
    revoke,
    revoke_all,
    set_cookie,
)
from backend.accounts.settings import (
    OAUTH_COOKIE,
    SESSION_COOKIE,
    chat_mode,
    google_client,
    public_base_url,
    secure_cookies,
)
from backend.storage.cache.redis import save_audit

config_router = APIRouter()
auth_router = APIRouter(prefix="/auth")
me_router = APIRouter(prefix="/me")

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_EMAIL = 254
_SUMMARY_FIELDS = ("degree", "level", "major", "catalog_year", "credits_applied", "credits_required", "audit_date")


def _error(detail: str, status: int) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _normal_email(email: str) -> str | None:
    email = (email or "").strip()
    if len(email) > _MAX_EMAIL or not _EMAIL.fullmatch(email):
        return None
    return email


# --------------------------------------------------------------------------- config


@config_router.get("/config")
def get_config():
    """Runtime switches the frontend needs (replaces the Streamlit env vars)."""
    return {
        "chat_mode": chat_mode(),
        "google_enabled": google_client() is not None,
        "email_enabled": mailer.enabled(),
        "audit_persistence": crypto.enabled(),
    }


# --------------------------------------------------------------------------- auth


class Credentials(BaseModel):
    email: str
    password: str


class TokenBody(BaseModel):
    token: str


class EmailBody(BaseModel):
    email: str


class ResetBody(BaseModel):
    token: str
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str | None = None
    new_password: str


def _user_by_id(conn, user_id) -> dict | None:
    return conn.execute(f"SELECT {USER_COLUMNS} FROM users u WHERE u.id = %s", (user_id,)).fetchone()


def _signed_in(conn, request: Request, user_id, status: int = 200) -> JSONResponse:
    token = create_session(conn, user_id, request)
    response = JSONResponse({"user": public_user(_user_by_id(conn, user_id))}, status_code=status)
    set_cookie(response, token)
    return response


@auth_router.post("/signup")
def signup(body: Credentials, request: Request):
    if not ratelimit.allow("signup", client_ip(request) or "?", 10, 3600):
        return _error("Too many sign-up attempts. Try again later.", 429)
    email = _normal_email(body.email)
    if email is None:
        return _error("Enter a valid email address.", 422)
    problem = password_problem(body.password)
    if problem:
        return _error(problem, 422)
    exists = "An account with this email already exists. Sign in instead."
    try:
        with db.connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (email,)).fetchone():
                return _error(exists, 409)
            row = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                (email, hash_password(body.password)),
            ).fetchone()
            user_id = row["id"]
            verify_token = tokens.issue(conn, user_id, "verify")
            log_event(conn, user_id, "sign_up", {"method": "password"}, request)
            response = _signed_in(conn, request, user_id, status=201)
    except psycopg.errors.UniqueViolation:  # lost a race with a simultaneous signup
        return _error(exists, 409)
    except psycopg.Error:
        return _error("database unavailable", 503)
    mailer.send_verification(email, verify_token)
    return response


@auth_router.post("/login")
def login(body: Credentials, request: Request):
    email = (body.email or "").strip()
    if not ratelimit.allow("login-ip", client_ip(request) or "?", 30, 900) or not ratelimit.allow(
        "login-email", email, 10, 900
    ):
        return _error("Too many sign-in attempts. Wait a few minutes and try again.", 429)
    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT id, password_hash FROM users WHERE lower(email) = lower(%s)", (email,)
            ).fetchone()
            if row is None or not verify_password(body.password, row["password_hash"]):
                return _error("Incorrect email or password.", 401)
            if needs_rehash(row["password_hash"]):
                conn.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (hash_password(body.password), row["id"]),
                )
            log_event(conn, row["id"], "sign_in", {"method": "password"}, request)
            return _signed_in(conn, request, row["id"])
    except psycopg.Error:
        return _error("database unavailable", 503)


@auth_router.post("/logout")
def logout(request: Request, user: dict | None = Depends(current_user_optional)):
    token = request.cookies.get(SESSION_COOKIE)
    try:
        with db.connect() as conn:
            if token:
                revoke(conn, token)
            if user is not None:
                log_event(conn, user["id"], "sign_out", {}, request)
    except psycopg.Error:
        pass
    response = Response(status_code=204)
    clear_cookie(response)
    return response


@auth_router.get("/me")
def me(user: dict | None = Depends(current_user_optional)):
    """The signed-in user, or {"user": null} for anonymous visitors."""
    return {"user": public_user(user) if user else None}


@auth_router.post("/verify")
def verify_email(body: TokenBody, request: Request):
    try:
        with db.connect() as conn:
            user_id = tokens.consume(conn, body.token, "verify")
            if user_id is None:
                return _error("This verification link is invalid or has expired.", 400)
            conn.execute(
                "UPDATE users SET email_verified_at = coalesce(email_verified_at, now()) WHERE id = %s",
                (user_id,),
            )
            log_event(conn, user_id, "email_verified", {}, request)
            return {"user": public_user(_user_by_id(conn, user_id))}
    except psycopg.Error:
        return _error("database unavailable", 503)


@auth_router.post("/verify/resend")
def resend_verification(request: Request, user: dict = Depends(require_user)):
    if user["email_verified_at"] is not None:
        return Response(status_code=204)
    if not mailer.enabled():
        return _error("Email is not configured on this server.", 503)
    if not ratelimit.allow("verify-resend", str(user["id"]), 5, 3600):
        return _error("Too many emails sent. Try again later.", 429)
    try:
        with db.connect() as conn:
            token = tokens.issue(conn, user["id"], "verify")
    except psycopg.Error:
        return _error("database unavailable", 503)
    if not mailer.send_verification(user["email"], token):
        return _error("The email could not be sent.", 503)
    return Response(status_code=204)


@auth_router.post("/password/forgot")
def forgot_password(body: EmailBody, request: Request):
    """Always 204, so the response never reveals whether an account exists."""
    email = (body.email or "").strip()
    if not mailer.enabled():
        return _error("Email is not configured on this server.", 503)
    if not ratelimit.allow("forgot-ip", client_ip(request) or "?", 10, 3600) or not ratelimit.allow(
        "forgot-email", email, 3, 3600
    ):
        return Response(status_code=204)
    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT id, email FROM users WHERE lower(email) = lower(%s)", (email,)
            ).fetchone()
            token = tokens.issue(conn, row["id"], "reset") if row else None
            if row:
                log_event(conn, row["id"], "password_reset_requested", {}, request)
    except psycopg.Error:
        return _error("database unavailable", 503)
    if row and token:
        mailer.send_password_reset(row["email"], token)
    return Response(status_code=204)


@auth_router.post("/password/reset")
def reset_password(body: ResetBody, request: Request):
    problem = password_problem(body.password)
    if problem:
        return _error(problem, 422)
    try:
        with db.connect() as conn:
            user_id = tokens.consume(conn, body.token, "reset")
            if user_id is None:
                return _error("This reset link is invalid or has expired.", 400)
            # Receiving the email proves the address, so it counts as verified too.
            conn.execute(
                """
                UPDATE users SET password_hash = %s,
                    email_verified_at = coalesce(email_verified_at, now())
                WHERE id = %s
                """,
                (hash_password(body.password), user_id),
            )
            revoke_all(conn, user_id)
            log_event(conn, user_id, "password_reset", {}, request)
    except psycopg.Error:
        return _error("database unavailable", 503)
    response = Response(status_code=204)
    clear_cookie(response)
    return response


@auth_router.post("/password/change")
def change_password(body: ChangePasswordBody, request: Request, user: dict = Depends(require_user)):
    problem = password_problem(body.new_password)
    if problem:
        return _error(problem, 422)
    try:
        with db.connect() as conn:
            stored = conn.execute(
                "SELECT password_hash FROM users WHERE id = %s", (user["id"],)
            ).fetchone()["password_hash"]
            if stored is not None and not verify_password(body.current_password or "", stored):
                return _error("Current password is incorrect.", 401)
            conn.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (hash_password(body.new_password), user["id"]),
            )
            revoke_all(conn, user["id"], keep_token=request.cookies.get(SESSION_COOKIE))
            log_event(conn, user["id"], "password_change", {}, request)
            return {"user": public_user(_user_by_id(conn, user["id"]))}
    except psycopg.Error:
        return _error("database unavailable", 503)


@auth_router.get("/google/login")
def google_login():
    if google_client() is None:
        return _error("Google sign-in is not configured.", 404)
    state, cookie = google.new_state()
    response = RedirectResponse(google.authorization_url(state), status_code=302)
    response.set_cookie(
        OAUTH_COOKIE, cookie, max_age=600, httponly=True, secure=secure_cookies(), samesite="lax", path="/"
    )
    return response


def _login_redirect(error: str) -> RedirectResponse:
    response = RedirectResponse(f"{public_base_url()}/login?error={error}", status_code=302)
    response.delete_cookie(OAUTH_COOKIE, path="/")
    return response


@auth_router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error or not code:
        return _login_redirect("google_cancelled")
    if not google.state_matches(state, request.cookies.get(OAUTH_COOKIE)):
        return _login_redirect("google_state")
    try:
        profile = google.fetch_profile(code)
    except Exception as exc:
        print(f"google sign-in failed: {exc!r}", file=sys.stderr)
        return _login_redirect("google")
    email_verified = bool(profile.get("email_verified"))
    try:
        with db.connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE google_sub = %s", (profile["sub"],)).fetchone()
            event = "sign_in"
            if row is None:
                row = conn.execute(
                    "SELECT id FROM users WHERE lower(email) = lower(%s)", (profile["email"],)
                ).fetchone()
                if row is not None:
                    if not email_verified:
                        return _login_redirect("google_unverified")
                    conn.execute(
                        """
                        UPDATE users SET google_sub = %s,
                            email_verified_at = coalesce(email_verified_at, now()),
                            display_name = coalesce(display_name, %s)
                        WHERE id = %s
                        """,
                        (profile["sub"], profile.get("name"), row["id"]),
                    )
                else:
                    row = conn.execute(
                        """
                        INSERT INTO users (email, google_sub, display_name, email_verified_at)
                        VALUES (%s, %s, %s, CASE WHEN %s THEN now() END) RETURNING id
                        """,
                        (profile["email"], profile["sub"], profile.get("name"), email_verified),
                    ).fetchone()
                    event = "sign_up"
            log_event(conn, row["id"], event, {"method": "google"}, request)
            token = create_session(conn, row["id"], request)
    except psycopg.Error:
        return _login_redirect("server")
    response = RedirectResponse(f"{public_base_url()}/", status_code=302)
    response.delete_cookie(OAUTH_COOKIE, path="/")
    set_cookie(response, token)
    return response


# --------------------------------------------------------------------------- /me


class ProfileBody(BaseModel):
    display_name: str | None = None


class MessageIn(BaseModel):
    role: str
    content: str
    sources: list[dict] | None = None


class MessagesBody(BaseModel):
    messages: list[MessageIn]


@me_router.patch("")
def update_profile(body: ProfileBody, request: Request, user: dict = Depends(require_user)):
    name = (body.display_name or "").strip()[:80] or None
    try:
        with db.connect() as conn:
            conn.execute("UPDATE users SET display_name = %s WHERE id = %s", (name, user["id"]))
            log_event(conn, user["id"], "profile_update", {}, request)
            return {"user": public_user(_user_by_id(conn, user["id"]))}
    except psycopg.Error:
        return _error("database unavailable", 503)


@me_router.delete("")
def delete_account(user: dict = Depends(require_user)):
    """Delete the account; every saved audit, search, message, session and log cascades."""
    try:
        with db.connect() as conn:
            conn.execute("DELETE FROM users WHERE id = %s", (user["id"],))
    except psycopg.Error:
        return _error("database unavailable", 503)
    response = Response(status_code=204)
    clear_cookie(response)
    return response


def _audit_row(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "filename": row["filename"],
        "summary": row["summary"],
        "created_at": _iso(row["created_at"]),
    }


@me_router.get("/audits")
def list_audits(user: dict = Depends(require_user)):
    try:
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, filename, summary, created_at FROM saved_audits
                WHERE user_id = %s ORDER BY created_at DESC LIMIT 50
                """,
                (user["id"],),
            ).fetchall()
    except psycopg.Error:
        return _error("database unavailable", 503)
    return {"audits": [_audit_row(row) for row in rows]}


def _load_saved_audit(conn, user_id, audit_id) -> dict | JSONResponse:
    row = conn.execute(
        "SELECT ciphertext FROM saved_audits WHERE id = %s AND user_id = %s", (audit_id, user_id)
    ).fetchone()
    if row is None:
        return _error("saved audit not found", 404)
    try:
        return crypto.decrypt_json(row["ciphertext"])
    except RuntimeError as exc:
        return _error(str(exc), 503)


def _cache_audit(audit: dict) -> str | JSONResponse:
    """Put a decrypted audit back in the Redis session cache under a new session id."""
    session_id = uuid.uuid4().hex
    try:
        save_audit(session_id, audit)
    except Exception:
        return _error("audit cache unavailable", 503)
    return session_id


@me_router.post("/audits/{audit_id}/load")
def load_saved_audit(audit_id: uuid.UUID, request: Request, user: dict = Depends(require_user)):
    try:
        with db.connect() as conn:
            audit = _load_saved_audit(conn, user["id"], audit_id)
            if isinstance(audit, JSONResponse):
                return audit
            session_id = _cache_audit(audit)
            if isinstance(session_id, JSONResponse):
                return session_id
            log_event(conn, user["id"], "audit_load", {"audit_id": str(audit_id)}, request)
    except psycopg.Error:
        return _error("database unavailable", 503)
    return {"session_id": session_id, "audit": audit, "audit_id": str(audit_id)}


@me_router.delete("/audits/{audit_id}")
def delete_saved_audit(audit_id: uuid.UUID, request: Request, user: dict = Depends(require_user)):
    try:
        with db.connect() as conn:
            deleted = conn.execute(
                "DELETE FROM saved_audits WHERE id = %s AND user_id = %s RETURNING id", (audit_id, user["id"])
            ).fetchone()
            if deleted is None:
                return _error("saved audit not found", 404)
            log_event(conn, user["id"], "audit_delete", {"audit_id": str(audit_id)}, request)
    except psycopg.Error:
        return _error("database unavailable", 503)
    return Response(status_code=204)


def _search_row(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "audit_id": str(row["audit_id"]) if row["audit_id"] else None,
        "soc_codes": list(row["soc_codes"]),
        "prefs": row["prefs"],
        "audit_summary": row.get("audit_summary"),
        "message_count": row.get("message_count", 0),
        "created_at": _iso(row["created_at"]),
    }


@me_router.get("/searches")
def list_searches(user: dict = Depends(require_user), limit: int = Query(30, ge=1, le=100)):
    try:
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.audit_id, s.soc_codes, s.prefs, s.created_at,
                       a.summary AS audit_summary,
                       (SELECT count(*) FROM chat_messages m WHERE m.search_id = s.id) AS message_count
                FROM searches s LEFT JOIN saved_audits a ON a.id = s.audit_id
                WHERE s.user_id = %s ORDER BY s.created_at DESC LIMIT %s
                """,
                (user["id"], limit),
            ).fetchall()
    except psycopg.Error:
        return _error("database unavailable", 503)
    return {"searches": [_search_row(row) for row in rows]}


def _messages(conn, search_id) -> list[dict]:
    rows = conn.execute(
        "SELECT role, content, sources, created_at FROM chat_messages WHERE search_id = %s ORDER BY id",
        (search_id,),
    ).fetchall()
    return [
        {"role": r["role"], "content": r["content"], "sources": r["sources"], "created_at": _iso(r["created_at"])}
        for r in rows
    ]


def _owned_search(conn, user_id, search_id) -> dict | None:
    return conn.execute(
        """
        SELECT s.id, s.audit_id, s.soc_codes, s.prefs, s.recommendation, s.created_at,
               a.summary AS audit_summary
        FROM searches s LEFT JOIN saved_audits a ON a.id = s.audit_id
        WHERE s.id = %s AND s.user_id = %s
        """,
        (search_id, user_id),
    ).fetchone()


@me_router.get("/searches/{search_id}")
def get_search(search_id: uuid.UUID, user: dict = Depends(require_user)):
    try:
        with db.connect() as conn:
            row = _owned_search(conn, user["id"], search_id)
            if row is None:
                return _error("search not found", 404)
            return {
                "search": {**_search_row(row), "recommendation": row["recommendation"]},
                "messages": _messages(conn, search_id),
            }
    except psycopg.Error:
        return _error("database unavailable", 503)


@me_router.post("/searches/{search_id}/restore")
def restore_search(search_id: uuid.UUID, request: Request, user: dict = Depends(require_user)):
    """Reopen a saved search: its audit goes back into the session cache, so the
    session-keyed endpoints (/recommend, /explain, /chat) work exactly as after an upload."""
    try:
        with db.connect() as conn:
            row = _owned_search(conn, user["id"], search_id)
            if row is None:
                return _error("search not found", 404)
            if row["audit_id"] is None:
                return _error("This search has no saved audit (it was deleted or never saved). Upload the audit again.", 410)
            audit = _load_saved_audit(conn, user["id"], row["audit_id"])
            if isinstance(audit, JSONResponse):
                return audit
            session_id = _cache_audit(audit)
            if isinstance(session_id, JSONResponse):
                return session_id
            messages = _messages(conn, search_id)
            log_event(conn, user["id"], "search_restore", {"search_id": str(search_id)}, request)
    except psycopg.Error:
        return _error("database unavailable", 503)
    recommendation = row["recommendation"]
    if isinstance(recommendation, dict):
        recommendation = {**recommendation, "session_id": session_id}
    return {
        "session_id": session_id,
        "audit": audit,
        "audit_id": str(row["audit_id"]),
        "search": {**_search_row(row), "recommendation": recommendation},
        "messages": messages,
    }


_MAX_MESSAGES = 10
_MAX_CONTENT = 20_000
_MAX_SOURCES = 25


@me_router.post("/searches/{search_id}/messages")
def append_messages(search_id: uuid.UUID, body: MessagesBody, user: dict = Depends(require_user)):
    """Save chat messages exactly as the page displayed them (seed, answers, fallbacks)."""
    if not body.messages or len(body.messages) > _MAX_MESSAGES:
        return _error(f"send 1 to {_MAX_MESSAGES} messages", 422)
    for message in body.messages:
        if message.role not in {"user", "assistant"}:
            return _error("role must be user or assistant", 422)
        if not message.content.strip() or len(message.content) > _MAX_CONTENT:
            return _error("message content is empty or too long", 422)
        if message.sources is not None and len(message.sources) > _MAX_SOURCES:
            return _error("too many sources", 422)
    try:
        with db.connect() as conn:
            if _owned_search(conn, user["id"], search_id) is None:
                return _error("search not found", 404)
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chat_messages (search_id, role, content, sources) VALUES (%s, %s, %s, %s)",
                    [
                        (search_id, m.role, m.content, Jsonb(m.sources) if m.sources is not None else None)
                        for m in body.messages
                    ],
                )
    except psycopg.Error:
        return _error("database unavailable", 503)
    return Response(status_code=204)


@me_router.delete("/searches/{search_id}")
def delete_search(search_id: uuid.UUID, request: Request, user: dict = Depends(require_user)):
    try:
        with db.connect() as conn:
            deleted = conn.execute(
                "DELETE FROM searches WHERE id = %s AND user_id = %s RETURNING id", (search_id, user["id"])
            ).fetchone()
            if deleted is None:
                return _error("search not found", 404)
            log_event(conn, user["id"], "search_delete", {"search_id": str(search_id)}, request)
    except psycopg.Error:
        return _error("database unavailable", 503)
    return Response(status_code=204)


@me_router.get("/activity")
def list_activity(
    user: dict = Depends(require_user),
    before: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, event, detail, ip, user_agent, created_at FROM activity_log
                WHERE user_id = %s AND (%s::bigint IS NULL OR id < %s)
                ORDER BY id DESC LIMIT %s
                """,
                (user["id"], before, before, limit + 1),
            ).fetchall()
    except psycopg.Error:
        return _error("database unavailable", 503)
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "events": [
            {
                "id": r["id"],
                "event": r["event"],
                "detail": r["detail"],
                "ip": r["ip"],
                "user_agent": r["user_agent"],
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ],
        "next_before": rows[-1]["id"] if more and rows else None,
    }


# ------------------------------------------- hooks used by the planning routes in main.py
# Best effort: a failure here is logged and never breaks the anonymous flow.


def audit_summary(audit: dict) -> dict:
    summary = {field: audit.get(field) for field in _SUMMARY_FIELDS}
    for key in ("courses_completed", "courses_in_progress", "courses_preregistered", "courses_not_taken"):
        summary[f"{key}_count"] = len(audit.get(key) or [])
    return summary


def persist_audit(user: dict | None, request: Request, filename: str | None, audit: dict) -> str | None:
    if user is None or not crypto.enabled():
        return None
    try:
        with db.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO saved_audits (user_id, filename, ciphertext, summary)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (user["id"], (filename or "")[:200] or None, crypto.encrypt_json(audit), Jsonb(audit_summary(audit))),
            ).fetchone()
            log_event(conn, user["id"], "audit_upload", {"audit_id": str(row["id"])}, request)
            return str(row["id"])
    except Exception as exc:
        print(f"saving audit failed: {exc!r}", file=sys.stderr)
        return None


def persist_search(
    user: dict | None,
    request: Request,
    audit_id: str | None,
    soc_codes: list[str],
    prefs: dict | None,
    recommendation: dict,
) -> str | None:
    if user is None:
        return None
    try:
        audit_uuid = uuid.UUID(audit_id) if audit_id else None
    except ValueError:
        audit_uuid = None
    try:
        with db.connect() as conn:
            if audit_uuid is not None and conn.execute(
                "SELECT 1 FROM saved_audits WHERE id = %s AND user_id = %s", (audit_uuid, user["id"])
            ).fetchone() is None:
                audit_uuid = None
            snapshot = {key: value for key, value in recommendation.items() if key != "session_id"}
            row = conn.execute(
                """
                INSERT INTO searches (user_id, audit_id, soc_codes, prefs, recommendation)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (user["id"], audit_uuid, soc_codes, Jsonb(prefs or {}), Jsonb(snapshot)),
            ).fetchone()
            log_event(
                conn,
                user["id"],
                "search",
                {"search_id": str(row["id"]), "soc_codes": soc_codes},
                request,
            )
            return str(row["id"])
    except Exception as exc:
        print(f"saving search failed: {exc!r}", file=sys.stderr)
        return None


def log_question(user: dict | None, request: Request, endpoint: str, search_id: str | None, question: str) -> None:
    if user is None:
        return
    try:
        with db.connect() as conn:
            log_event(
                conn,
                user["id"],
                "question",
                {"endpoint": endpoint, "search_id": search_id, "question": question[:500]},
                request,
            )
    except Exception as exc:
        print(f"logging question failed: {exc!r}", file=sys.stderr)
