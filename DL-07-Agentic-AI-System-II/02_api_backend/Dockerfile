# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- base
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

# The upstream slim image lags Debian security fixes; take them at build time (D-100).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv

# ---------------------------------------------------------------- deps
FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---------------------------------------------------------------- dev
FROM deps AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project
COPY . .
USER app
EXPOSE 8000
CMD ["python", "-m", "app.serve", "--reload"]

# ---------------------------------------------------------------- runtime
FROM base AS runtime
# Several uvicorn workers (and Celery pool processes) share their metrics here (D-91).
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
COPY --from=deps /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app alembic.ini ./
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
# Validates configuration first and exits with code 2 if it is invalid.
CMD ["python", "-m", "app.serve", "--workers", "2"]
