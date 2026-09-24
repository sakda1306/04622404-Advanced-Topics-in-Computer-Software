from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .audit import AuditStore, AuditUnavailable
from .config import Settings
from .emergency import EmergencyCatalog
from .models import DecisionRequest, DecisionResponse
from .policy import Policy
from .service import decide


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    policy = Policy.load(settings.decision_policy_version)
    catalog = EmergencyCatalog.load(settings.emergency_catalog_path)
    audit = AuditStore(settings.audit_log_path)
    app = FastAPI(
        title="Team D — Module 07 Decision Engine",
        version="0.3.0",
        description="Standalone prototype with a draft contract and unapproved mock policy.",
    )
    app.state.settings = settings
    app.state.audit = audit
    if settings.llm_model_explainer != "disabled" and settings.llm_api_key.get_secret_value():
        from .provider import GeminiExplanationProvider
        app.state.provider = GeminiExplanationProvider(settings)
    else:
        app.state.provider = None
    app.state.clock = lambda: datetime.now(UTC)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        # Pydantic's default error includes original input; never echo private payloads.
        return JSONResponse(
            status_code=422,
            content={
                "code": "INVALID_INPUT",
                "errors": [{"location": list(e["loc"]), "type": e["type"]} for e in error.errors()],
            },
        )

    @app.get("/health")
    async def health():
        return {"status": "ok", "module": "07", "prototype_only": True}

    @app.get("/ready")
    async def ready():
        if not audit.check():
            raise HTTPException(status_code=503, detail={"code": "AUDIT_UNAVAILABLE"})
        return {"status": "ready", "policy": policy.version, "policy_status": "prototype"}

    @app.post("/v1/decisions", response_model=DecisionResponse)
    async def decisions(body: DecisionRequest):
        if body.locale not in settings.locales:
            raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_LOCALE"})
        try:
            return await decide(
                body,
                now=app.state.clock(),
                settings=settings,
                policy=policy,
                audit=audit,
                emergency_catalog=catalog,
                provider=app.state.provider,
            )
        except AuditUnavailable:
            raise HTTPException(status_code=503, detail={"code": "AUDIT_UNAVAILABLE"}) from None

    return app


app = create_app()
