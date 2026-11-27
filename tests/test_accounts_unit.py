"""Account building blocks that need no database: hashing, encryption, CSRF, OAuth state."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.accounts import crypto, google, passwords
from backend.accounts.csrf import OriginCheckMiddleware


def test_password_hash_round_trip_and_rejects_wrong_password():
    stored = passwords.hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert passwords.verify_password("correct horse battery", stored)
    assert not passwords.verify_password("correct horse batterY", stored)
    assert not passwords.verify_password("anything", None)
    assert not passwords.verify_password("anything", "garbage")
    assert not passwords.needs_rehash(stored)
    assert passwords.needs_rehash("scrypt$14$8$1$abc$def")


def test_same_password_gets_different_salts():
    assert passwords.hash_password("same password") != passwords.hash_password("same password")


def test_password_rules():
    assert passwords.password_problem("short") is not None
    assert passwords.password_problem(" " * 10) is not None
    assert passwords.password_problem("x" * 300) is not None
    assert passwords.password_problem("long enough") is None


def test_audit_encryption_round_trip_and_rotation(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("AUDIT_ENCRYPTION_KEY", old)
    audit = {"major": "Computer Science", "courses_completed": [{"code": "ITSC 1212"}]}
    token = crypto.encrypt_json(audit)
    assert b"Computer Science" not in token
    assert crypto.decrypt_json(token) == audit
    # Rotate: the new key encrypts, the old one still decrypts existing rows.
    monkeypatch.setenv("AUDIT_ENCRYPTION_KEY", f"{new},{old}")
    assert crypto.decrypt_json(token) == audit
    monkeypatch.setenv("AUDIT_ENCRYPTION_KEY", new)
    with pytest.raises(RuntimeError):
        crypto.decrypt_json(token)


def test_encryption_disabled_without_valid_key(monkeypatch):
    monkeypatch.delenv("AUDIT_ENCRYPTION_KEY", raising=False)
    assert not crypto.enabled()
    monkeypatch.setenv("AUDIT_ENCRYPTION_KEY", "not-a-key")
    assert not crypto.enabled()
    with pytest.raises(RuntimeError):
        crypto.encrypt_json({})


def _csrf_client(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8501")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    app = FastAPI()
    app.add_middleware(OriginCheckMiddleware)

    @app.post("/thing")
    def thing():
        return {"ok": True}

    @app.get("/thing")
    def read():
        return {"ok": True}

    return TestClient(app)


def test_csrf_allows_same_origin_and_headerless(monkeypatch):
    client = _csrf_client(monkeypatch)
    assert client.post("/thing", headers={"Origin": "http://localhost:8501"}).status_code == 200
    assert client.post("/thing").status_code == 200
    assert client.post("/thing", headers={"Referer": "http://localhost:8501/login"}).status_code == 200


def test_csrf_rejects_foreign_origin(monkeypatch):
    client = _csrf_client(monkeypatch)
    assert client.post("/thing", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/thing", headers={"Origin": "null"}).status_code == 403
    assert client.post("/thing", headers={"Referer": "https://evil.example/x"}).status_code == 403
    # Same-origin requests pass even when the host differs from PUBLIC_BASE_URL
    # (e.g. the app opened at 127.0.0.1 instead of localhost).
    assert client.post("/thing", headers={"Origin": "http://testserver"}).status_code == 200
    assert client.post("/thing", headers={"Origin": "http://127.0.0.1:8501", "Host": "127.0.0.1:8501"}).status_code == 200
    assert client.post("/thing", headers={"Origin": "https://evil.example", "Host": "127.0.0.1:8501"}).status_code == 403
    # Safe methods are never blocked.
    assert client.get("/thing", headers={"Origin": "https://evil.example"}).status_code == 200


def test_google_state_is_signed():
    state, cookie = google.new_state()
    assert google.state_matches(state, cookie)
    assert not google.state_matches("other", cookie)
    assert not google.state_matches(state, cookie[:-1] + ("0" if cookie[-1] != "0" else "1"))
    assert not google.state_matches(state, None)
