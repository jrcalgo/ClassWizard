import os
import re
import uuid
from dataclasses import asdict

import psycopg
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.storage.cache.redis import delete_audit, load_audit, ping, save_audit
from data.degreeworks.parser import parse_audit

_SESSION_ID = re.compile(r"[0-9a-f]{32}")

app = FastAPI()

# Computer science and IT roles only. Order is the menu order.
OCCUPATION_CATEGORIES = [
    (
        "Software and programming",
        ["15-1251.00", "15-1252.00", "15-1253.00", "15-1299.08"],
    ),
    (
        "Web and interface",
        ["15-1254.00", "15-1255.00", "15-1255.01", "15-1299.01"],
    ),
    (
        "Data and databases",
        ["15-1242.00", "15-1243.00", "15-1243.01", "15-2051.00", "15-2051.01"],
    ),
    (
        "Networks and systems",
        ["15-1231.00", "15-1232.00", "15-1241.00", "15-1244.00"],
    ),
    (
        "Security",
        ["15-1212.00", "15-1299.04", "15-1299.05", "15-1299.06"],
    ),
    (
        "IT management and analysis",
        ["11-3021.00", "15-1211.00", "15-1221.00", "15-1299.09"],
    ),
]


@app.get("/health")
def health():
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            row = conn.execute(
                "SELECT 1, '[1,0,0]'::vector <=> '[0,1,0]'::vector"
            ).fetchone()
        if row is None or row[0] != 1:
            raise RuntimeError("postgres query failed")
        if not ping():
            raise RuntimeError("redis ping failed")
    except Exception:
        return PlainTextResponse("unavailable", status_code=500)
    return PlainTextResponse("OK")


@app.get("/occupations")
def occupations():
    codes = [code for _, group in OCCUPATION_CATEGORIES for code in group]
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            rows = conn.execute(
                """
                SELECT soc_code, title
                FROM occupations
                WHERE soc_code = ANY(%s)
                """,
                (codes,),
            ).fetchall()
    except Exception:
        return JSONResponse({"detail": "occupations unavailable"}, status_code=503)
    titles = {soc: title for soc, title in rows}
    categories = []
    for name, group in OCCUPATION_CATEGORIES:
        items = [
            {"soc_code": code, "title": titles[code]}
            for code in group
            if code in titles
        ]
        items.sort(key=lambda item: item["title"])
        categories.append({"name": name, "occupations": items})
    return {"categories": categories}


def _session_id(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    token = value.strip()
    if _SESSION_ID.fullmatch(token) is None:
        return None
    return token


@app.post("/audit")
async def post_audit(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
):
    """Parse one DegreeWorks PDF and store it for this page session."""
    token = _session_id(session_id)
    if session_id and session_id.strip() and token is None:
        return JSONResponse({"detail": "invalid session"}, status_code=422)
    if token is None:
        token = uuid.uuid4().hex
    try:
        audit = asdict(parse_audit(await file.read()))
    except Exception:
        return JSONResponse({"detail": "audit could not be parsed"}, status_code=422)
    try:
        save_audit(token, audit)
    except Exception:
        return JSONResponse({"detail": "audit cache unavailable"}, status_code=503)
    return {"session_id": token, "audit": audit}


@app.get("/audit/{session_id}")
def get_audit(session_id: str):
    """Return the stored audit and extend its TTL."""
    if _session_id(session_id) is None:
        return JSONResponse({"detail": "audit not found"}, status_code=404)
    try:
        audit = load_audit(session_id)
    except Exception:
        return JSONResponse({"detail": "audit cache unavailable"}, status_code=503)
    if audit is None:
        return JSONResponse({"detail": "audit not found"}, status_code=404)
    return {"session_id": session_id, "audit": audit}


@app.delete("/audit/{session_id}")
def remove_audit(session_id: str):
    """Drop the stored audit when its Streamlit session ends."""
    if _session_id(session_id) is None:
        return JSONResponse({"detail": "audit not found"}, status_code=404)
    try:
        delete_audit(session_id)
    except Exception:
        return JSONResponse({"detail": "audit cache unavailable"}, status_code=503)
    return PlainTextResponse("", status_code=204)
