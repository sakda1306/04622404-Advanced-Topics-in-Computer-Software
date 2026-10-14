#!/usr/bin/env sh
# Start-up of the `api` container: migrate, seed (idempotent), serve.
set -eu

alembic upgrade head
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
