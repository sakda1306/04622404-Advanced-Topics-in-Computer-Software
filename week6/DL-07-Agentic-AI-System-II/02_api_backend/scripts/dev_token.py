"""Print a short-lived dev access token.

Usage: python -m scripts.dev_token [--sub dev-user] [--scope travel:read ...] [--minutes 15]
Needs APP_ENV=dev/test and DEV_JWT_SIGNING_KEY; never works in staging or production.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import timedelta

from app.core.config import AppSettings, AuthSettings
from app.core.security import Scope, issue_dev_token

DEFAULT_SCOPES = [Scope.TRAVEL_READ, Scope.TRAVEL_WRITE, Scope.PROFILE_READ, Scope.PROFILE_WRITE]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.dev_token")
    parser.add_argument("--sub", default="dev-user")
    parser.add_argument("--scope", action="append", choices=[s.value for s in Scope])
    parser.add_argument("--minutes", type=int, default=15)
    args = parser.parse_args(argv)

    if AppSettings().is_production:
        print("dev tokens are disabled outside dev/test", file=sys.stderr)
        return 2
    auth = AuthSettings()
    if auth.dev_jwt_signing_key is None:
        print("set DEV_JWT_SIGNING_KEY (at least 32 characters) first", file=sys.stderr)
        return 2

    token = issue_dev_token(
        auth,
        subject=args.sub,
        scopes=args.scope or DEFAULT_SCOPES,
        lifetime=timedelta(minutes=args.minutes),
    )
    print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
