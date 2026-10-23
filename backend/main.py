import os

import psycopg
import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

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
        if not redis.Redis.from_url(os.environ["REDIS_URL"]).ping():
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
