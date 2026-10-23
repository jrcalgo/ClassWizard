#!/bin/bash
set -euo pipefail

: "${POSTGRES_USER:=classwizard}"
: "${POSTGRES_PASSWORD:=classwizard}"
: "${POSTGRES_DB:=classwizard}"
: "${DATABASE_URL:=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}}"
: "${REDIS_URL:=redis://127.0.0.1:6379/0}"
export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL REDIS_URL PGPASSWORD="$POSTGRES_PASSWORD"

docker-entrypoint.sh postgres &
pg_pid=$!

until pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  && psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
       "SELECT 1 FROM pg_extension WHERE extname = 'vector'" | grep -q 1
do
  if ! kill -0 "$pg_pid" 2>/dev/null; then
    echo "postgres exited before it was ready" >&2
    exit 1
  fi
  sleep 1
done

redis-server --daemonize yes --bind 127.0.0.1 --protected-mode yes --port 6379

cd /app
python3 -m backend.storage.database.postgres

cleanup() {
  kill "$pg_pid" 2>/dev/null || true
  redis-cli shutdown nosave || true
}
trap cleanup EXIT INT TERM

uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
wait $!
