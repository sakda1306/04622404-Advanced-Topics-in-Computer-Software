"""Operational endpoints: /health (E-25), /ready (E-26), /metrics (E-27).

/ready and /metrics answer only callers inside OPS_ALLOWED_NETWORKS. The client address
is the one uvicorn resolved from trusted proxies, so a request that came in through the
public ingress carries the user's address and gets 404 (D-90).
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.deps import get_ops_service
from app.api.resources import get_resources
from app.core import metrics
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.infrastructure.health import queue_depth
from app.services.ops_service import OpsService
from app.workers.celery_app import ALERT_QUEUE, MAINTENANCE_QUEUE, RECOMMENDATION_QUEUE

router = APIRouter(tags=["ops"])
log = get_logger(__name__)

QUEUES = (RECOMMENDATION_QUEUE, ALERT_QUEUE, MAINTENANCE_QUEUE)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


def internal_only(request: Request) -> None:
    networks = get_resources(request).settings.observability.ops_allowed_networks
    host = request.client.host if request.client else None
    try:
        address = ip_address(host) if host else None
    except ValueError:
        address = None
    if address is None or not any(address in ip_network(net, strict=False) for net in networks):
        # Pretend the endpoint does not exist rather than advertise it.
        raise AppError(ErrorCode.NOT_FOUND)


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    # Liveness only: never check dependencies here, or a DB outage restarts every pod.
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness probe (internal)",
    responses={503: {"model": ReadyResponse}},
    dependencies=[Depends(internal_only)],
)
async def ready(ops: OpsService = Depends(get_ops_service)) -> JSONResponse:
    result = await ops.readiness()
    body = ReadyResponse(status="ready" if result.ready else "not_ready", checks=result.checks)
    return JSONResponse(
        body.model_dump(),
        status_code=200 if result.ready else 503,
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/metrics",
    summary="Prometheus metrics (internal)",
    response_class=Response,
    dependencies=[Depends(internal_only)],
)
async def prometheus_metrics(request: Request) -> Response:
    depth = None
    redis = get_resources(request).redis
    if redis is not None and redis.broker is not None:
        try:
            depth = await queue_depth(redis.broker, QUEUES)
        except Exception as exc:  # the rest of the metrics are still worth serving
            log.warning("queue_depth_unavailable", error_type=type(exc).__name__)
    return Response(
        metrics.render(depth),
        media_type=metrics.CONTENT_TYPE,
        headers={"Cache-Control": "no-store"},
    )
