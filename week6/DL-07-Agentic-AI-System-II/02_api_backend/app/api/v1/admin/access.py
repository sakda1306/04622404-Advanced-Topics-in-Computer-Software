"""Scope check for admin routes that also audits refusals (D-95).

A caller with a valid token but without the scope gets 403 and one `denied` audit row
(subject, action, required scope, ip hash). The per-user rate limit (P-30) already
applies, so refusals cannot flood the audit log faster than any other request.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request

from app.api.audit import client_ip_hash, correlation_id
from app.api.auth import ensure_scopes, get_principal
from app.api.deps import get_audit
from app.core.logging import get_logger
from app.core.security import Principal, Scope
from app.domain.enums import AuditResult
from app.services.admin_service import Actor, write_admin_audit
from app.services.ports import AuditPort

log = get_logger(__name__)


def admin_actor(scope: Scope, action: str) -> Callable[..., Awaitable[Actor]]:
    async def dependency(
        request: Request,
        principal: Principal = Depends(get_principal),
        audit: AuditPort | None = Depends(get_audit),
    ) -> Actor:
        actor = Actor(principal.subject, correlation_id(), client_ip_hash(request))
        if not principal.has_scopes((scope,)) and audit is not None:
            try:
                await write_admin_audit(
                    audit,
                    actor,
                    action,
                    AuditResult.DENIED,
                    metadata={"required_scope": scope.value},
                )
            except Exception as exc:  # the refusal must not turn into a 500
                log.warning("audit_write_failed", action=action, error_type=type(exc).__name__)
        ensure_scopes(principal, scope)
        return actor

    return dependency
