"""Process lifecycle of a Celery worker: logging, tracing and the metrics endpoint.

The main process starts the /metrics server before the pool forks; each pool process
sets up logging and tracing for itself, because exporter threads do not survive fork.
With PROMETHEUS_MULTIPROC_DIR set, the server adds up the numbers of all pool
processes (D-91).
"""

from __future__ import annotations

import os
from typing import Any

from celery.signals import celeryd_init, worker_process_init, worker_process_shutdown
from prometheus_client import start_http_server

from app.core import metrics
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import setup_tracing, shutdown_tracing
from app.workers.runtime import runtime

log = get_logger(__name__)


@celeryd_init.connect
def start_metrics_server(**_: Any) -> None:
    port = get_settings().observability.worker_metrics_port
    if port == 0:
        return
    metrics.reset_multiprocess_dir()
    start_http_server(port, registry=metrics.collecting_registry())
    log.info("worker_metrics_listening", port=port)


@worker_process_init.connect
def init_process(**_: Any) -> None:
    settings = get_settings()
    configure_logging(
        level=settings.observability.log_level, json_output=settings.observability.log_json
    )
    setup_tracing(settings.observability)


@worker_process_shutdown.connect
def close_process(**_: Any) -> None:
    runtime.close()
    shutdown_tracing()
    metrics.mark_process_dead(os.getpid())
