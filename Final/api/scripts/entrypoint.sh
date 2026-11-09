#!/usr/bin/env sh
# Start-up of the `api` container: migrate, then serve with one worker (Design.md §8).
set -eu

mkdir -p var
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers
