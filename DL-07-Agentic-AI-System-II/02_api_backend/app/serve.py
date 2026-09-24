"""Process entrypoint: `python -m app.serve`.

Settings are validated here, in the supervisor process, before any worker starts.
With `uvicorn --workers N` a worker that fails at import is restarted forever, so a
missing variable would leave the container running but never healthy.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import uvicorn
from pydantic import ValidationError

from app.core import metrics
from app.core.config import Settings, get_settings

EXIT_CONFIG_ERROR = 2
APP_FACTORY = "app.main:create_app"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="app.serve", description="Run the backend API")
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container listens on all interfaces
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--reload", action="store_true", help="development only")
    return parser.parse_args(argv)


def _config_errors() -> list[str]:
    """Validate every settings group so all problems are reported in one run."""
    failures: list[ValidationError] = []
    for field in Settings.model_fields.values():
        factory = field.default_factory
        if factory is None:
            continue
        try:
            factory()  # type: ignore[call-arg]
        except ValidationError as exc:
            failures.append(exc)
    if not failures:
        get_settings.cache_clear()
        try:
            get_settings()
        except ValidationError as exc:
            failures.append(exc)

    messages = []
    for failure in failures:
        # include_input=False: invalid values may be secrets such as DATABASE_URL.
        for error in failure.errors(include_input=False, include_url=False, include_context=False):
            field_name = ".".join(str(part) for part in error["loc"]) or failure.title
            messages.append(f"config error: {field_name}: {error['msg']}")
    return messages


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    errors = _config_errors()
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        print("refusing to start: fix the configuration above", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    settings = get_settings()
    # Metric files of the previous run would otherwise be added to the new counts.
    metrics.reset_multiprocess_dir()

    uvicorn.run(
        APP_FACTORY,
        factory=True,
        host=args.host,
        port=args.port,
        workers=1 if args.reload else args.workers,
        reload=args.reload,
        reload_dirs=["app"] if args.reload else None,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips=settings.app.forwarded_allow_ips,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
