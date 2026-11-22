import os
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict

import psycopg
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ai.nlp.explanations.llm import explain
from ai.nlp.explanations.rag import (
    build_messages,
    check_citations,
    generate,
    keep_cited,
    model_name,
    student_context,
)
from ai.nlp.explanations.retrieval import retrieve_evidence
from ai.recommendations.ranking import MissingVectors, UnsupportedAudit, audit_level, recommend
from backend.storage.cache.redis import delete_audit, load_audit, ping, save_audit
from backend.storage.database.pgvector import search_syllabus_triples
from data.degreeworks.parser import parse_audit

_SESSION_ID = re.compile(r"[0-9a-f]{32}")
_ENCODER = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def _load_encoder() -> None:
    """Load the syllabus embedding model once. Weights are baked into the image."""
    global _ENCODER
    from sentence_transformers import SentenceTransformer

    _ENCODER = SentenceTransformer(_MODEL_NAME, local_files_only=True)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _load_encoder()
    yield


app = FastAPI(lifespan=_lifespan)

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


_CURATED_SOC = {code for _, group in OCCUPATION_CATEGORIES for code in group}
_MAX_CAREERS = 5
_MAX_LIMIT = 25


class RecommendRequest(BaseModel):
    """Body of POST /recommend."""

    session_id: str
    soc_codes: list[str]
    limit: int = 10


@app.post("/recommend")
def post_recommend(body: RecommendRequest):
    """Rank the stored audit's still-needed courses against the chosen careers."""
    checked = _session_and_careers(body.session_id, body.soc_codes)
    if isinstance(checked, JSONResponse):
        return checked
    token, soc_codes, audit = checked
    if not 1 <= body.limit <= _MAX_LIMIT:
        return JSONResponse({"detail": f"limit must be 1 to {_MAX_LIMIT}"}, status_code=422)
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            result = recommend(conn, audit, soc_codes, body.limit)
    except UnsupportedAudit as exc:
        # e.g. "the Graduate 2026-2027 catalog is not loaded yet"
        return JSONResponse({"detail": str(exc)}, status_code=422)
    except MissingVectors as exc:
        return JSONResponse({"detail": str(exc)}, status_code=409)
    except psycopg.Error:
        return JSONResponse({"detail": "database unavailable"}, status_code=503)
    return {"session_id": token, **result}


def _session_and_careers(session_id: str, soc_codes: list[str]):
    """Shared checks for /recommend and /explain.

    Returns (token, soc_codes, audit), or a JSONResponse describing the error.
    """
    token = _session_id(session_id)
    if token is None:
        return JSONResponse({"detail": "invalid session"}, status_code=422)
    soc_codes = list(dict.fromkeys(soc_codes))  # drop repeats, keep order
    if not soc_codes or len(soc_codes) > _MAX_CAREERS:
        return JSONResponse({"detail": f"choose 1 to {_MAX_CAREERS} careers"}, status_code=422)
    if any(code not in _CURATED_SOC for code in soc_codes):
        return JSONResponse({"detail": "unknown career"}, status_code=422)
    try:
        audit = load_audit(token)
    except Exception:
        return JSONResponse({"detail": "audit cache unavailable"}, status_code=503)
    if audit is None:
        return JSONResponse({"detail": "audit not found"}, status_code=404)
    return token, soc_codes, audit


_MAX_QUESTION = 500


class ExplainRequest(BaseModel):
    """Body of POST /explain."""

    session_id: str
    soc_codes: list[str]
    question: str


@app.post("/explain")
def post_explain(body: ExplainRequest):
    """Answer a question about the student's recommendations from cited evidence only.

    Runs next to /chat: /chat answers from syllabus triples through the
    provider chosen in llm.py; /explain answers from catalog, O*NET and
    /recommend evidence through a local Ollama model (rag.py).
    """
    question = " ".join(body.question.split())
    if not question or len(question) > _MAX_QUESTION:
        return JSONResponse(
            {"detail": f"question must be 1 to {_MAX_QUESTION} characters"}, status_code=422
        )
    checked = _session_and_careers(body.session_id, body.soc_codes)
    if isinstance(checked, JSONResponse):
        return checked
    token, soc_codes, audit = checked
    # 1-2. Context and retrieval: recompute the recommendation server-side
    # (never trust a course list from the client), then gather evidence.
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            recommendation = recommend(conn, audit, soc_codes, _MAX_LIMIT)
            evidence = retrieve_evidence(conn, question, audit, recommendation, soc_codes)
    except UnsupportedAudit as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    except MissingVectors as exc:
        return JSONResponse({"detail": str(exc)}, status_code=409)
    except psycopg.Error:
        return JSONResponse({"detail": "database unavailable"}, status_code=503)
    # 3-4. Prompt and generation. If the model is unreachable, still return
    # the evidence so the frontend can show the facts.
    messages = build_messages(question, evidence, student_context(audit))
    try:
        answer = keep_cited(generate(messages))
    except Exception:
        _renew_audit(token)
        return JSONResponse(
            {"detail": "language model unavailable", "evidence": evidence}, status_code=503
        )
    # Generation can take minutes on CPU, during which the page cannot renew
    # the audit; renew it now so the page's next refresh still finds it.
    _renew_audit(token)
    # 5. Citation check: every cited ID must be one of the evidence IDs.
    return {
        "session_id": token,
        "answer": answer,
        **check_citations(answer, evidence),
        "evidence": evidence,
        "model": model_name(),
    }


def _renew_audit(token: str) -> None:
    """Slide the audit's TTL forward. Best effort: a cache error must not lose the answer."""
    try:
        load_audit(token)
    except Exception:
        pass


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


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: list[dict] = Field(default_factory=list)
    prefs: dict = Field(default_factory=dict)


def _retrieve(question: str, audit: dict) -> list[dict]:
    # Search with the question alone; the audit still reaches the model in the prompt.
    if _ENCODER is None:
        raise RuntimeError("encoder not loaded")
    vector = _ENCODER.encode(question.strip()).tolist()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        level = (audit_level(audit) or "").lower() or None
        return search_syllabus_triples(conn, vector, top_k=5, level=level)


@app.post("/chat")
def post_chat(body: ChatRequest):
    """Answer from syllabus triples and the stored DegreeWorks audit."""
    if _session_id(body.session_id) is None:
        return JSONResponse({"detail": "audit not found"}, status_code=404)
    if not body.message.strip():
        return JSONResponse({"detail": "message required"}, status_code=422)
    try:
        audit = load_audit(body.session_id)
    except Exception:
        return JSONResponse({"detail": "audit cache unavailable"}, status_code=503)
    if audit is None:
        return JSONResponse({"detail": "audit not found"}, status_code=404)
    try:
        rows = _retrieve(body.message, audit)
        reply = explain(body.message, body.history, audit, body.prefs, rows)
    except RuntimeError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    except Exception:
        return JSONResponse({"detail": "reply unavailable"}, status_code=503)
    if not reply:
        return JSONResponse({"detail": "reply unavailable"}, status_code=503)
    return {"reply": reply}
