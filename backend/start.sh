#!/bin/bash
set -euo pipefail

: "${POSTGRES_USER:=classwizard}"
: "${POSTGRES_PASSWORD:=classwizard}"
: "${POSTGRES_DB:=classwizard}"
: "${DATABASE_URL:=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}}"
: "${REDIS_URL:=redis://redis:6379/0}"
export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL REDIS_URL PGPASSWORD="$POSTGRES_PASSWORD"

# Postgres and Redis are separate containers. This process only waits for them.

python3 - <<'PY'
import os
import sys
import time

import psycopg
import redis

deadline = time.time() + 120
last = "not started"
while time.time() <= deadline:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as conn:
            row = conn.execute(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
        if row is None:
            last = "vector extension missing"
        else:
            redis.Redis.from_url(
                os.environ["REDIS_URL"], socket_connect_timeout=3
            ).ping()
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as exc:
        last = str(exc)
    time.sleep(1)

print(f"postgres/redis not ready: {last}", file=sys.stderr)
raise SystemExit(1)
PY

cd /app
python3 -m backend.storage.database.postgres
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
