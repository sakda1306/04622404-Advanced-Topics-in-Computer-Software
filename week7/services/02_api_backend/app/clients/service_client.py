"""JSON client for internal services (07 football-data, 05 retrieval).

Every call forwards X-Request-ID. Problem-JSON codes the web app needs to see (for
example 409 JOB_ALREADY_RUNNING from 07) are passed through; anything else from the
other side becomes `<service>_UNAVAILABLE` (502).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.errors import AppError, ErrorCode
from app.core.ids import current_request_id
from app.core.logging import get_logger

log = get_logger(__name__)

_PASS_THROUGH = frozenset(
    {
        ErrorCode.NOT_FOUND,
        ErrorCode.VALIDATION_ERROR,
        ErrorCode.JOB_ALREADY_RUNNING,
        ErrorCode.REPORT_NOT_EDITABLE,
        ErrorCode.REPORT_ALREADY_PUBLISHED,
        ErrorCode.MATCHWEEK_NOT_COMPLETE,
        ErrorCode.QUOTA_EXHAUSTED,
        ErrorCode.INDEX_UPDATE_FAILED,
        ErrorCode.SIMULATION_UNAVAILABLE,
    }
)


def _problem_code(response: httpx.Response) -> ErrorCode | None:
    try:
        body = response.json()
    except ValueError:
        return None
    code = body.get("code") if isinstance(body, dict) else None
    try:
        return ErrorCode(code) if isinstance(code, str) else None
    except ValueError:
        return None


class ServiceClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str,
        timeout_seconds: float,
        service: str,
        unavailable: ErrorCode,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._service = service
        self._unavailable = unavailable

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            response = await self._http.request(
                method,
                f"{self._base_url}{path}",
                params=clean_params or None,
                json=json,
                headers={"X-Request-ID": current_request_id()},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            log.warning("service_call_failed", service=self._service, error_type=type(exc).__name__)
            raise AppError(self._unavailable, log_context={"service": self._service}) from exc

        if response.is_success:
            try:
                return response.json()
            except ValueError as exc:
                raise AppError(self._unavailable, log_context={"service": self._service}) from exc

        code = _problem_code(response)
        if response.status_code == 404:
            code = ErrorCode.NOT_FOUND
        if code in _PASS_THROUGH:
            assert code is not None
            retry = response.headers.get("retry-after", "")
            raise AppError(code, retry_after=int(retry) if retry.isdigit() else None)
        log.warning("service_call_failed", service=self._service, status=response.status_code)
        raise AppError(
            self._unavailable,
            log_context={"service": self._service, "status": response.status_code},
        )

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, body: Any) -> Any:
        return await self.request("POST", path, json=body)

    async def patch(self, path: str, body: Any) -> Any:
        return await self.request("PATCH", path, json=body)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)
