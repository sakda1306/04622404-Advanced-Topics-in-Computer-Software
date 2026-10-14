"""Smoke-check live Compose services from inside its network (no provider calls)."""

from __future__ import annotations

import json
import os
import sys
import http.cookiejar
import urllib.error
import urllib.request


def request(url: str, *, cookie: str | None = None) -> tuple[int, dict]:
    headers = {"Cookie": cookie} if cookie else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def login_and_check(username: str, password: str, expected_admin_status: int) -> None:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    payload = json.dumps({"username": username, "password": password}).encode()
    login = urllib.request.Request(
        "http://api:8000/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(login, timeout=15) as response:
        if response.status != 200:
            raise ValueError(f"{username} login returned {response.status}")
    try:
        with opener.open("http://api:8000/api/admin/stats", timeout=15) as response:
            actual = response.status
    except urllib.error.HTTPError as exc:
        actual = exc.code
    if actual != expected_admin_status:
        raise ValueError(f"{username} admin stats: expected {expected_admin_status}, got {actual}")


def main() -> int:
    endpoints = {
        "web": "http://web:3000/health",
        "api": "http://api:8000/ready",
        "router": "http://router:8000/health",
        "engines": "http://engines:8000/health",
        "retrieval": "http://retrieval:8000/ready",
        "generation": "http://generation:8000/health",
        "football-data": "http://football-data:8000/ready",
    }
    failures: list[str] = []
    for name, url in endpoints.items():
        try:
            status, body = request(url)
            if status != 200 or body.get("status") != "ok":
                failures.append(f"{name}: HTTP {status}, {body.get('status')}")
            else:
                print(f"OK {name}")
        except (OSError, ValueError) as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    try:
        status, _ = request("http://api:8000/api/admin/stats")
        if status != 401:
            failures.append(f"admin without login: expected 401, got {status}")
        else:
            print("OK admin requires authentication")
    except (OSError, ValueError) as exc:
        failures.append(f"admin access check: {type(exc).__name__}: {exc}")

    credential_checks = (
        ("demo1", os.getenv("SEED_DEMO_PASSWORD"), 403),
        ("admin", os.getenv("SEED_ADMIN_PASSWORD"), 200),
    )
    total = len(endpoints) + 1
    for username, password, expected in credential_checks:
        if not password:
            failures.append(f"{username}: seed password is missing; smoke needs seeded accounts")
        else:
            try:
                login_and_check(username, password, expected)
                print(f"OK {username} access")
            except (OSError, ValueError) as exc:
                failures.append(f"{username} access: {type(exc).__name__}: {exc}")
        total += 1

    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    print(f"{total - len(failures)}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
