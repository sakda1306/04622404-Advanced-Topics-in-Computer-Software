"""Write the current OpenAPI schema to openapi.json for the Web App team (`make openapi`).

Building the app only needs Settings — no DB, Redis or Agent connection is made — so
this runs standalone, without docker compose. Values here are only defaults: a real
`.env` or already-exported environment variables take precedence.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://tsa:tsa@localhost:5432/tsa")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_ISSUER", "http://localhost:8000/dev-issuer")
os.environ.setdefault("JWT_AUDIENCE", "travel-safety-api")
os.environ.setdefault("AGENT_SERVICE_URL", "http://localhost:8010")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from app.main import create_app

OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> int:
    schema = create_app().openapi()
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    OUTPUT.write_bytes(text.encode("utf-8"))  # avoid CRLF from write_text on Windows
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
