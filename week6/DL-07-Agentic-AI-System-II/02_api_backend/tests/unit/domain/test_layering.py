"""The domain layer stays framework-free (docs/04_project_structure.md section 2)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

DOMAIN = Path(__file__).resolve().parents[3] / "app" / "domain"
FORBIDDEN = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "geoalchemy2",
    "redis",
    "httpx",
    "pydantic",
    "app.api",
    "app.schemas",
    "app.infrastructure",
    "app.services",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


# The only application modules the domain may use (docs/04_project_structure.md §2).
ALLOWED_APP_MODULES = ("app.domain", "app.core.geo", "app.core.clock")


@pytest.mark.parametrize("path", sorted(DOMAIN.glob("*.py")), ids=lambda p: p.name)
def test_domain_module_has_no_framework_imports(path: Path) -> None:
    bad = {name for name in _imports(path) if name.startswith(FORBIDDEN)}

    assert bad == set()


@pytest.mark.parametrize("path", sorted(DOMAIN.glob("*.py")), ids=lambda p: p.name)
def test_domain_module_uses_only_allowed_app_modules(path: Path) -> None:
    app_imports = {name for name in _imports(path) if name == "app" or name.startswith("app.")}

    assert {name for name in app_imports if not name.startswith(ALLOWED_APP_MODULES)} == set()
