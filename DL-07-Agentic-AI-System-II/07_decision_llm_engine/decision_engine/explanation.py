import asyncio
import json
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .models import Action, DecisionRequest, Explanation
from .policy import Decision


class Candidate(BaseModel):
    """Constrained structured-output seam; no live model is configured in this prototype.

    Candidate text must use the supplied sentence bank verbatim. This deliberately
    restrictive prototype cannot invent a number, citation or emergency instruction.
    Expand it only with reviewed semantic validation and real-provider evaluation.
    """

    model_config = ConfigDict(extra="forbid")
    action_code: Action
    summary: str = Field(max_length=2000)
    reasons: list[str] = Field(max_length=16)
    instructions: list[str] = Field(max_length=16)
    uncertainty: list[str] = Field(max_length=16)
    evidence_ids: list[str] = Field(max_length=64)


class ExplanationProvider(Protocol):
    async def generate(self, package: dict, *, max_output_tokens: int) -> dict: ...


def fixed_explanation(decision: Decision, locale: str) -> Explanation:
    content = json.loads((Path(__file__).parent / "templates" / "v1.json").read_text("utf-8"))
    texts = content[locale]
    # Only trusted, versioned template text enters Jinja. Never render RAG excerpts.
    template = Environment(undefined=StrictUndefined, autoescape=True).from_string("{{ text }}")
    instructions = [texts["instruction"]]
    if decision.escalation_required:
        instructions.append(texts["review_instruction"])
    return Explanation(
        summary=template.render(text=texts["summaries"][decision.action]),
        reasons=[texts["reasons"][decision.rule_id]],
        instructions=instructions,
        uncertainty=[texts["uncertainty"]] if decision.issues else [],
        mode="template",
    )


async def explain(
    decision: Decision,
    request: DecisionRequest,
    settings: Settings,
    provider: ExplanationProvider | None,
    citation_ids: list[str],
) -> tuple[Explanation, list[str]]:
    fallback = fixed_explanation(decision, request.locale)
    if provider is None:
        return fallback, ["LLM_DISABLED_TEMPLATE_USED"]
    ids = sorted(citation_ids)
    is_nl = getattr(provider, "is_natural_language", False)
    package = {
        "system": "Explain the locked action using only the supplied sentence bank. "
        "Never change its meaning, numbers, instructions or evidence IDs.",
        "locked_action": decision.action.value,
        "prompt_version": settings.prompt_version,
        "temperature": settings.temperature,
        "sentence_bank": fallback.model_dump(exclude={"mode"}),
        "evidence_ids": ids,
        "output_schema": Candidate.model_json_schema(),
    }
    if is_nl:
        risk_level = None
        if request.risk:
            risk_level = getattr(request.risk.level, "value", str(request.risk.level))

        package["context_summary"] = {
            "route_id": request.context.route_id,
            "departure_time": request.context.departure_time.isoformat(),
            "weather_summary": request.weather.text if request.weather else None,
            "transport_summary": request.transport.text if request.transport else None,
            "risk_level": risk_level,
            "alerts": [
                f"Level: {alert.level}, Active: {alert.active}" for alert in request.alerts
            ],
        }
    # Byte length is a conservative upper bound for byte-level tokenizer input.
    # Real provider integrations must replace this with that provider's token counter.
    packed = json.dumps(package, ensure_ascii=False).encode("utf-8")
    if len(packed) > settings.max_input_tokens:
        return fallback, ["LLM_INPUT_BUDGET_TEMPLATE_USED"]
    failures = []

    async def attempts():
        is_nl = getattr(provider, "is_natural_language", False)
        for _ in range(settings.llm_max_attempts):
            try:
                # Each attempt gets a fresh copy; it cannot mutate the locked decision.
                raw = await provider.generate(
                    json.loads(packed), max_output_tokens=settings.max_output_tokens
                )
                if len(json.dumps(raw, ensure_ascii=False).encode()) > settings.max_output_tokens:
                    failures.append("LLM_OUTPUT_BUDGET")
                    continue
                candidate = Candidate.model_validate(raw)
                if is_nl:
                    valid = (
                        candidate.action_code == decision.action
                        and bool(candidate.summary and candidate.summary.strip())
                        and bool(candidate.reasons)
                        and bool(candidate.instructions)
                        and set(candidate.evidence_ids).issubset(set(ids))
                    )
                else:
                    valid = (
                        candidate.action_code == decision.action
                        and candidate.summary == fallback.summary
                        and sorted(candidate.reasons) == sorted(fallback.reasons)
                        and sorted(candidate.instructions) == sorted(fallback.instructions)
                        and sorted(candidate.uncertainty) == sorted(fallback.uncertainty)
                        and sorted(candidate.evidence_ids) == ids
                    )
                if not valid:
                    failures.append("LLM_UNGROUNDED_OUTPUT")
                    continue
                return Explanation(
                    summary=candidate.summary,
                    reasons=candidate.reasons,
                    instructions=candidate.instructions,
                    uncertainty=candidate.uncertainty,
                    mode="provider",
                )
            except Exception:
                # Do not log provider errors: they can contain API keys or prompt text.
                failures.append("LLM_PROVIDER_OR_SCHEMA_ERROR")
        return None

    try:
        async with asyncio.timeout(settings.llm_timeout):
            result = await attempts()
    except TimeoutError:
        failures.append("LLM_TIMEOUT")
        result = None
    if result is not None:
        return result, [*failures, "LLM_OUTPUT_VALIDATED"]
    return fallback, [*failures, "LLM_INVALID_OR_UNAVAILABLE_TEMPLATE_USED"]
