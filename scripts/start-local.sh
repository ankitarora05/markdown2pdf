#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

docker compose up -d --wait postgres

export DATABASE_URL="${LOCAL_DATABASE_URL:-postgresql+psycopg://markdown2pdf:markdown2pdf_local@127.0.0.1:5433/markdown2pdf}"
export COOKIE_SECURE=false

exec uvicorn app.main:app --reload --host 127.0.0.1 --port "${LOCAL_APP_PORT:-8000}"
