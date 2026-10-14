"""Where the standalone scripts find the repo .env."""

from pathlib import Path


def repo_env_file(service_root: Path) -> Path | None:
    """The repo-root .env in a checkout; None in the Docker image (/app), where env vars are set."""
    parents = service_root.parents
    return parents[1] / ".env" if len(parents) > 1 else None
