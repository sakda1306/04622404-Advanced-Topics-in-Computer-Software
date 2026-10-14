"""Start and wait for the 07 fixtures ingest before a live demonstration."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


BASE = os.getenv("FOOTBALL_DATA_URL", "http://football-data:8000").rstrip("/")


def call(path: str, body: dict | None = None) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=payload,
        headers={"Content-Type": "application/json"} if payload else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from 07: {detail}") from exc


def main() -> int:
    if not os.getenv("FOOTBALL_DATA_API_KEY"):
        print("Set FOOTBALL_DATA_API_KEY in .env before warmup.", file=sys.stderr)
        return 2
    job = call("/ingest/run", {"scope": "fixtures", "triggered_by": "beat"})
    job_id = job["job_id"]
    print(f"Started fixtures ingest {job_id}")
    for _ in range(60):
        time.sleep(5)
        result = call(f"/jobs/{job_id}")
        status = result.get("status")
        if status == "done":
            print("Fixtures ingest finished.")
            return 0
        if status == "failed":
            print(f"Fixtures ingest failed: {result}", file=sys.stderr)
            return 1
    print(f"Fixtures ingest did not finish within five minutes: {job_id}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
