#!/usr/bin/env sh
# Start-up of the `retrieval` container: load the trivia file (unchanged entries are
# skipped), then serve. One worker only: the index lives in this process's memory.
set -eu

python -m scripts.ingest_trivia
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
