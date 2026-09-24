"""Request details for the audit log (D-70)."""

from __future__ import annotations

from fastapi import Request

from app.api.resources import get_resources
from app.core.crypto import keyed_hash
from app.core.ids import current_correlation_id, current_request_id, new_id


def client_ip_hash(request: Request) -> str:
    # request.client already reflects X-Forwarded-For from trusted proxies only.
    address = request.client.host if request.client else "unknown"
    return keyed_hash(get_resources(request).settings.secrets.ip_hash_secret, address)


def correlation_id() -> str:
    return current_correlation_id() or current_request_id() or str(new_id())
