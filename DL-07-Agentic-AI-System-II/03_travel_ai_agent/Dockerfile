# syntax=docker/dockerfile:1

FROM python:3.12-slim AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
WORKDIR /app
COPY 03_travel_ai_agent/pyproject.toml 03_travel_ai_agent/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --home-dir /app --no-create-home app
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY 03_travel_ai_agent/travel_agent ./travel_agent
# 04/05/06 currently expose Python adapters, not network services. Keep only the
# runtime files Module 03 calls, under the same sibling names used in the repo.
COPY 04_external_data_services/tomtom_transport.py \
     04_external_data_services/longdo_traffic_adapter.py \
     04_external_data_services/gdacs_adapter.py \
     04_external_data_services/thai_disaster_adapter.py \
     04_external_data_services/weather_service.py \
     04_external_data_services/open_meteo_adapter.py \
     04_external_data_services/weather_to_canonical.py \
     04_external_data_services/route_candidates.py \
     ./04_external_data_services/
COPY 05_data_integration/integration.py ./05_data_integration/integration.py
COPY 06_risk_knowledge_services/risk_knowledge ./06_risk_knowledge_services/risk_knowledge
USER 10001:10001
EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=2)"]
CMD ["uvicorn", "travel_agent.api:app", "--host", "0.0.0.0", "--port", "8010"]
