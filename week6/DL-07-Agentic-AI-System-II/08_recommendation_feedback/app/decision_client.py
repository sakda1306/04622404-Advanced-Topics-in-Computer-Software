"""
HTTP client for Module 07 (Decision & LLM Engine).

Connects to 07's FastAPI app (`POST /v1/decisions`) to retrieve real-time,
audited safety decisions.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx
import structlog
from fastapi import HTTPException

from app.config import settings

logger = structlog.get_logger("decision_client")


class DecisionEngineClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = (base_url or settings.decision_engine_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.decision_engine_timeout_seconds
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    async def check_health(self) -> bool:
        """Ping 07 health endpoint to verify connectivity."""
        try:
            async with self._get_client() as client:
                res = await client.get("/health")
                return res.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.warning("decision_engine_health_failed", error=str(exc))
            return False

    async def request_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Send a DecisionRequest payload to Module 07 (`POST /v1/decisions`)
        and return the validated DecisionResponse dict.
        """
        url = f"{self.base_url}/v1/decisions"
        logger.info("requesting_decision_from_07", url=url)

        try:
            async with self._get_client() as client:
                response = await client.post("/v1/decisions", json=payload)
        except httpx.ConnectError as exc:
            logger.error("decision_engine_connect_error", error=str(exc), url=url)
            raise HTTPException(
                status_code=503,
                detail="Decision engine (Module 07) is unreachable",
            ) from exc
        except httpx.TimeoutException as exc:
            logger.error("decision_engine_timeout", error=str(exc), url=url)
            raise HTTPException(
                status_code=504,
                detail="Decision engine (Module 07) request timed out",
            ) from exc
        except httpx.RequestError as exc:
            logger.error("decision_engine_request_error", error=str(exc), url=url)
            raise HTTPException(
                status_code=502,
                detail=f"Decision engine request failed: {str(exc)}",
            ) from exc

        if response.status_code == 422:
            logger.warning("decision_engine_validation_error", response=response.text)
            raise HTTPException(
                status_code=422,
                detail=response.json(),
            )

        if response.status_code != 200:
            logger.error(
                "decision_engine_error_response",
                status_code=response.status_code,
                response=response.text,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Decision engine returned HTTP {response.status_code}: {response.text}",
            )

        return response.json()
