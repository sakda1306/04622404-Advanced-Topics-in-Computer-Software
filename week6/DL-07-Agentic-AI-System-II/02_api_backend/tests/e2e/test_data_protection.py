"""End-to-end checks of step 5.9b: data export, encryption at rest and the purge job.

The encryption and purge checks read PostgreSQL through `docker compose exec`, so they
also need the docker CLI.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import time
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from tests.e2e.test_me_jobs import token
from tests.e2e.test_recommendation_flow import BASE_URL, body, post

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not BASE_URL, reason="E2E_BASE_URL is not set"),
]

PROJECT = Path(__file__).resolve().parents[2]
DOCKER = shutil.which("docker")
needs_docker = pytest.mark.skipif(DOCKER is None, reason="docker CLI is not available")


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        yield client


def compose(*args: str) -> str:
    assert DOCKER is not None
    done = subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [DOCKER, "compose", *args], cwd=PROJECT, check=True, capture_output=True, timeout=60
    )
    return done.stdout.decode()


def psql(sql: str) -> str:
    return compose("exec", "-T", "postgres", "psql", "-U", "tsa", "-d", "tsa", "-At", "-c", sql)


def test_data_export(api: httpx.Client) -> None:
    jwt = token(f"e2e-{uuid4()}")
    auth = {"Authorization": f"Bearer {jwt}"}
    asked = post(api, jwt, body(question="E2E export question"), mode="sync")
    assert asked.status_code == 200, asked.text

    accepted = api.post("/v1/me/data-export", headers={**auth, "Idempotency-Key": str(uuid4())})
    again = api.post("/v1/me/data-export", headers={**auth, "Idempotency-Key": str(uuid4())})
    assert accepted.status_code == 202, accepted.text
    assert again.status_code == 429

    deadline = time.monotonic() + 30
    status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status = api.get(accepted.headers["Location"], headers=auth).json()
        if status["status"] in ("ready", "failed"):
            break
        time.sleep(0.5)
    assert status["status"] == "ready", status
    download = httpx.get(status["download_url"], timeout=10)
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        data = json.loads(archive.read("travel-safety-data.json"))
    me = api.get("/v1/me", headers=auth).json()
    assert data["profile"]["user_id"] == me["user_id"]
    messages = [m["content"] for c in data["conversations"] for m in c["messages"]]
    assert "E2E export question" in messages


@needs_docker
def test_free_text_is_encrypted_in_the_database(api: httpx.Client) -> None:
    marker = f"secret-{uuid4().hex[:8]}"
    jwt = token(f"e2e-{uuid4()}")
    assert post(api, jwt, body(question=marker), mode="sync").status_code == 200

    stored = psql("SELECT content FROM messages ORDER BY created_at DESC LIMIT 20")

    assert marker not in stored
    assert "enc:v1:" in stored


@needs_docker
def test_purge_job_keeps_audit_partitions_ahead() -> None:
    compose(
        "exec", "-T", "worker",
        "celery", "-A", "app.workers.celery_app:celery_app", "call",
        "app.workers.tasks.maintenance.purge_expired", "--queue", "maintenance",
    )  # fmt: skip
    now = datetime.now(UTC)
    expected = f"audit_logs_y{now.year:04d}m{now.month:02d}"

    deadline = time.monotonic() + 30
    partitions = ""
    while time.monotonic() < deadline:
        partitions = psql(
            "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "JOIN pg_class p ON p.oid = i.inhparent WHERE p.relname = 'audit_logs'"
        )
        if expected in partitions:
            break
        time.sleep(0.5)
    assert expected in partitions
    assert "retention.purge" in psql(
        "SELECT action FROM audit_logs WHERE action = 'retention.purge' LIMIT 1"
    )
