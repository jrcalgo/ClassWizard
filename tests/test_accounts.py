"""Account flows against a real PostgreSQL in an isolated schema (skips without DATABASE_URL).

Redis is replaced by fakeredis; email is captured instead of sent.
"""
import os
import re
from pathlib import Path
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
fakeredis = pytest.importorskip("fakeredis")
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

ORIGIN = "http://localhost:8501"


@pytest.fixture
def api(monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL required")
    from backend.accounts import db, mailer, ratelimit, routes
    from backend.accounts.csrf import OriginCheckMiddleware

    schema = "test_accounts_" + uuid4().hex
    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
        try:
            def scoped(*args, **kwargs):
                return psycopg.connect(url, options=f"-c search_path={schema},public", row_factory=dict_row)

            with scoped() as conn:
                conn.execute(Path("backend/accounts_schema.sql").read_text())
            monkeypatch.setattr(db, "connect", scoped)

            fake = fakeredis.FakeRedis()
            monkeypatch.setattr(ratelimit, "_client", lambda: fake)
            cached = {}
            monkeypatch.setattr(routes, "save_audit", lambda sid, audit: cached.__setitem__(sid, audit))

            outbox = []
            monkeypatch.setenv("SMTP_HOST", "mail.test")
            monkeypatch.setattr(mailer, "send", lambda to, subject, body: outbox.append((to, subject, body)) or True)
            monkeypatch.setenv("PUBLIC_BASE_URL", ORIGIN)
            monkeypatch.setenv("AUDIT_ENCRYPTION_KEY", Fernet.generate_key().decode())

            app = FastAPI()
            app.add_middleware(OriginCheckMiddleware)
            app.include_router(routes.config_router)
            app.include_router(routes.auth_router)
            app.include_router(routes.me_router)

            @app.post("/fake-upload")
            def fake_upload(request: routes.Request, user=routes.Depends(routes.current_user_optional)):
                audit = {"major": "Computer Science", "catalog_year": "2025-2026", "courses_completed": []}
                return {"audit_id": routes.persist_audit(user, request, "audit.pdf", audit)}

            @app.post("/fake-search")
            def fake_search(body: dict, request: routes.Request, user=routes.Depends(routes.current_user_optional)):
                result = {"recommendations": [{"code": "ITSC 3160"}], "session_id": "x" * 32}
                return {"search_id": routes.persist_search(user, request, body.get("audit_id"), ["15-1252.00"], {"credits": 15}, result)}

            client = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
            yield client, outbox, cached, scoped
        finally:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")


def _token(outbox, kind):
    body = outbox[-1][2]
    return re.search(rf"/{kind}\?token=([\w-]+)", body).group(1)


def test_signup_login_me_logout(api):
    client, outbox, _, _ = api
    assert client.get("/auth/me").json() == {"user": None}

    r = client.post("/auth/signup", json={"email": "Student@Example.edu", "password": "password123"})
    assert r.status_code == 201, r.text
    user = r.json()["user"]
    assert user["email"] == "Student@Example.edu" and not user["email_verified"]
    assert "cw_session" in r.cookies
    assert outbox and "/verify?token=" in outbox[-1][2]
    assert client.get("/auth/me").json()["user"]["id"] == user["id"]

    assert client.post("/auth/signup", json={"email": "student@example.edu", "password": "password123"}).status_code == 409

    assert client.post("/auth/logout").status_code == 204
    client.cookies.clear()
    assert client.get("/auth/me").json() == {"user": None}

    assert client.post("/auth/login", json={"email": "student@example.edu", "password": "wrong-password"}).status_code == 401
    r = client.post("/auth/login", json={"email": "student@example.edu", "password": "password123"})
    assert r.status_code == 200 and r.json()["user"]["id"] == user["id"]


def test_logout_revokes_the_session_server_side(api):
    client, _, _, _ = api
    client.post("/auth/signup", json={"email": "a@b.co", "password": "password123"})
    stolen = client.cookies.get("cw_session")
    client.post("/auth/logout")
    client.cookies.clear()
    client.cookies.set("cw_session", stolen)
    assert client.get("/auth/me").json() == {"user": None}


def test_signup_validation(api):
    client, _, _, _ = api
    assert client.post("/auth/signup", json={"email": "not-an-email", "password": "password123"}).status_code == 422
    assert client.post("/auth/signup", json={"email": "a@b.co", "password": "short"}).status_code == 422


def test_email_verification_is_single_use(api):
    client, outbox, _, _ = api
    client.post("/auth/signup", json={"email": "v@b.co", "password": "password123"})
    token = _token(outbox, "verify")
    r = client.post("/auth/verify", json={"token": token})
    assert r.status_code == 200 and r.json()["user"]["email_verified"]
    assert client.post("/auth/verify", json={"token": token}).status_code == 400
    assert client.post("/auth/verify", json={"token": "made-up"}).status_code == 400


def test_password_reset_flow(api):
    client, outbox, _, _ = api
    client.post("/auth/signup", json={"email": "r@b.co", "password": "password123"})
    client.cookies.clear()
    # Unknown emails get the same answer and no email.
    sent = len(outbox)
    assert client.post("/auth/password/forgot", json={"email": "nobody@b.co"}).status_code == 204
    assert len(outbox) == sent
    assert client.post("/auth/password/forgot", json={"email": "R@b.co"}).status_code == 204
    token = _token(outbox, "reset")
    assert client.post("/auth/password/reset", json={"token": token, "password": "brand-new-pass"}).status_code == 204
    assert client.post("/auth/password/reset", json={"token": token, "password": "another-pass1"}).status_code == 400
    assert client.post("/auth/login", json={"email": "r@b.co", "password": "password123"}).status_code == 401
    r = client.post("/auth/login", json={"email": "r@b.co", "password": "brand-new-pass"})
    assert r.status_code == 200 and r.json()["user"]["email_verified"]


def test_expired_reset_token_is_refused(api):
    client, outbox, _, scoped = api
    client.post("/auth/signup", json={"email": "e@b.co", "password": "password123"})
    client.post("/auth/password/forgot", json={"email": "e@b.co"})
    token = _token(outbox, "reset")
    with scoped() as conn:
        conn.execute("UPDATE email_tokens SET expires_at = now() - interval '1 minute' WHERE purpose = 'reset'")
    assert client.post("/auth/password/reset", json={"token": token, "password": "brand-new-pass"}).status_code == 400


def test_login_is_rate_limited(api):
    client, _, _, _ = api
    codes = [
        client.post("/auth/login", json={"email": "x@b.co", "password": "wrong-password"}).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_cross_site_post_is_refused(api):
    client, _, _, _ = api
    r = client.post(
        "/auth/signup", json={"email": "c@b.co", "password": "password123"}, headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403


def test_me_routes_require_sign_in(api):
    client, _, _, _ = api
    assert client.get("/me/searches").status_code == 401
    assert client.get("/me/activity").status_code == 401
    assert client.delete("/me").status_code == 401


def test_saved_search_restore_and_activity(api):
    client, _, cached, scoped = api
    client.post("/auth/signup", json={"email": "s@b.co", "password": "password123"})
    audit_id = client.post("/fake-upload").json()["audit_id"]
    assert audit_id
    with scoped() as conn:
        raw = conn.execute("SELECT ciphertext FROM saved_audits").fetchone()["ciphertext"]
    assert b"Computer Science" not in bytes(raw)  # encrypted at rest

    search_id = client.post("/fake-search", json={"audit_id": audit_id}).json()["search_id"]
    assert search_id
    r = client.post(
        f"/me/searches/{search_id}/messages",
        json={"messages": [{"role": "user", "content": "Why ITSC 3160?"}, {"role": "assistant", "content": "Because.", "sources": [{"id": "c1", "kind": "course", "text": "t"}]}]},
    )
    assert r.status_code == 204

    searches = client.get("/me/searches").json()["searches"]
    assert [s["id"] for s in searches] == [search_id]
    assert searches[0]["message_count"] == 2
    assert searches[0]["audit_summary"]["major"] == "Computer Science"

    restored = client.post(f"/me/searches/{search_id}/restore").json()
    assert cached[restored["session_id"]]["major"] == "Computer Science"
    assert restored["search"]["recommendation"]["session_id"] == restored["session_id"]
    assert [m["role"] for m in restored["messages"]] == ["user", "assistant"]

    events = [e["event"] for e in client.get("/me/activity").json()["events"]]
    assert {"sign_up", "audit_upload", "search", "search_restore"} <= set(events)

    # Deleting the audit keeps the search but restore explains why it cannot reopen.
    assert client.delete(f"/me/audits/{audit_id}").status_code == 204
    assert client.post(f"/me/searches/{search_id}/restore").status_code == 410


def test_other_users_cannot_see_my_data(api):
    client, _, _, _ = api
    client.post("/auth/signup", json={"email": "one@b.co", "password": "password123"})
    audit_id = client.post("/fake-upload").json()["audit_id"]
    search_id = client.post("/fake-search", json={"audit_id": audit_id}).json()["search_id"]
    client.post("/auth/logout")
    client.cookies.clear()
    client.post("/auth/signup", json={"email": "two@b.co", "password": "password123"})
    assert client.get(f"/me/searches/{search_id}").status_code == 404
    assert client.post(f"/me/audits/{audit_id}/load").status_code == 404
    assert client.delete(f"/me/searches/{search_id}").status_code == 404
    # A foreign audit id is not linked to my search.
    mine = client.post("/fake-search", json={"audit_id": audit_id}).json()["search_id"]
    assert client.get(f"/me/searches/{mine}").json()["search"]["audit_id"] is None


def test_delete_account_cascades(api):
    client, _, _, scoped = api
    client.post("/auth/signup", json={"email": "d@b.co", "password": "password123"})
    audit_id = client.post("/fake-upload").json()["audit_id"]
    client.post("/fake-search", json={"audit_id": audit_id})
    assert client.delete("/me").status_code == 204
    with scoped() as conn:
        for table in ("users", "user_sessions", "email_tokens", "saved_audits", "searches", "chat_messages", "activity_log"):
            assert conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0, table


def test_change_password_keeps_current_session_and_revokes_others(api):
    client, _, _, _ = api
    client.post("/auth/signup", json={"email": "p@b.co", "password": "password123"})
    other = TestClient(client.app, base_url=ORIGIN, headers={"Origin": ORIGIN})
    other.post("/auth/login", json={"email": "p@b.co", "password": "password123"})
    assert other.get("/auth/me").json()["user"] is not None
    assert client.post("/auth/password/change", json={"current_password": "nope-nope", "new_password": "newpassword1"}).status_code == 401
    assert client.post("/auth/password/change", json={"current_password": "password123", "new_password": "newpassword1"}).status_code == 200
    assert client.get("/auth/me").json()["user"] is not None
    assert other.get("/auth/me").json()["user"] is None


def test_config_reports_features(api):
    client, _, _, _ = api
    config = client.get("/config").json()
    assert config["email_enabled"] and config["audit_persistence"]
    assert config["chat_mode"] in {"explain", "chat"}


# ---------------------------------------------------------------- Google sign-in
# Google itself is mocked: fetch_profile stands in for the token exchange and
# userinfo call; everything else (state cookie, linking, sessions) is real.


def _google(api, monkeypatch, profile):
    from backend.accounts import google, routes

    client = api[0]
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(routes.google, "fetch_profile", lambda code: profile)
    start = client.get("/auth/google/login", follow_redirects=False)
    assert start.status_code == 302
    location = start.headers["location"]
    assert location.startswith(google.AUTH_URL)
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8501%2Fapi%2Fauth%2Fgoogle%2Fcallback" in location
    state = re.search(r"state=([^&]+)", location).group(1)
    return client, state


def test_google_login_disabled_without_credentials(api, monkeypatch):
    client = api[0]
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert client.get("/auth/google/login", follow_redirects=False).status_code == 404
    assert client.get("/config").json()["google_enabled"] is False


def test_google_sign_up_creates_verified_user(api, monkeypatch):
    client, state = _google(api, monkeypatch, {"sub": "g-1", "email": "g@example.edu", "email_verified": True, "name": "Gee"})
    r = client.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "http://localhost:8501/"
    user = client.get("/auth/me").json()["user"]
    assert user["email"] == "g@example.edu" and user["email_verified"] and user["google_linked"]
    assert not user["has_password"] and user["display_name"] == "Gee"


def test_google_links_existing_password_account_by_verified_email(api, monkeypatch):
    client = api[0]
    client.post("/auth/signup", json={"email": "link@example.edu", "password": "password123"})
    first = client.get("/auth/me").json()["user"]["id"]
    client.post("/auth/logout")
    client.cookies.clear()
    client, state = _google(api, monkeypatch, {"sub": "g-2", "email": "LINK@example.edu", "email_verified": True})
    client.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    user = client.get("/auth/me").json()["user"]
    assert user["id"] == first and user["google_linked"] and user["has_password"]


def test_google_refuses_unverified_email_for_existing_account(api, monkeypatch):
    client = api[0]
    client.post("/auth/signup", json={"email": "u@example.edu", "password": "password123"})
    client.post("/auth/logout")
    client.cookies.clear()
    client, state = _google(api, monkeypatch, {"sub": "g-3", "email": "u@example.edu", "email_verified": False})
    r = client.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert r.headers["location"].endswith("/login?error=google_unverified")
    assert client.get("/auth/me").json()["user"] is None


def test_google_callback_rejects_forged_state_and_cancel(api, monkeypatch):
    client, _ = _google(api, monkeypatch, {"sub": "g-4", "email": "f@example.edu", "email_verified": True})
    r = client.get("/auth/google/callback?code=abc&state=forged", follow_redirects=False)
    assert r.headers["location"].endswith("/login?error=google_state")
    r = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
    assert r.headers["location"].endswith("/login?error=google_cancelled")
    assert client.get("/auth/me").json()["user"] is None
