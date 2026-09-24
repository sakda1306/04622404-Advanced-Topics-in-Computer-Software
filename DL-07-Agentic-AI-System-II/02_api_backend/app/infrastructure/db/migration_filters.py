"""Autogenerate filters shared by migrations/env.py and the schema drift test."""

from __future__ import annotations

from typing import Any

from geoalchemy2 import alembic_helpers


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    # Ignore database objects that are not ours: PostGIS tables (spatial_ref_sys,
    # tiger/topology) and the audit_logs partitions.
    if type_ == "table" and reflected and compare_to is None:
        return False
    included = alembic_helpers.include_object(  # type: ignore[no-untyped-call]
        obj, name, type_, reflected, compare_to
    )
    return bool(included)
