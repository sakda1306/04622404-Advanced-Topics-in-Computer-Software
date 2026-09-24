# syntax=docker/dockerfile:1

FROM python:3.12-slim AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    AUDIT_LOG_PATH=/app/data/audit.jsonl
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --home-dir /app --no-create-home app \
    && mkdir -p /app/data \
    && chown app:app /app/data
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY decision_engine ./decision_engine
USER 10001:10001
EXPOSE 8050
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8050/health', timeout=2)"]
CMD ["uvicorn", "decision_engine.api:app", "--host", "0.0.0.0", "--port", "8050"]
