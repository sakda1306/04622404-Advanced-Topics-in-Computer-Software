"""Read-only contract tests across the current 05 -> 06 -> 03 -> 07 boundary.

The sibling modules are imported as dependencies but never modified. Provider calls
are not made: synthetic canonical records exercise their real integration/adapters.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from decision_engine.api import create_app
from decision_engine.config import Settings
from decision_engine.emergency import EmergencyCatalog

MODULES = Path(__file__).resolve().parents[2]
MODULE_03 = MODULES / "03_travel_ai_agent"
MODULE_05 = MODULES / "05_data_integration" / "integration.py"
MODULE_06 = MODULES / "06_risk_knowledge_services"

if not all(path.exists() for path in (MODULE_03, MODULE_05, MODULE_06)):
    pytest.skip("Sibling modules are absent in this standalone checkout", allow_module_level=True)

for path in (MODULE_03, MODULE_06):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from risk_knowledge.knowledge import retrieve_knowledge  # noqa: E402 # type: ignore
from risk_knowledge.risk import assess_risk  # noqa: E402 # type: ignore
from risk_knowledge.routing import analyze_routes  # noqa: E402 # type: ignore
from travel_agent.evidence import build_decision_request  # noqa: E402 # type: ignore
from travel_agent.tools.schemas import (  # noqa: E402 # type: ignore
    DisasterResult,
    IntegratedContext,
    Record,
    RiskResult,
    RouteResult,
    TransportResult,
    WeatherResult,
)

NOW = datetime(2026, 9, 21, 1, 0, tzinfo=UTC)
DEPARTURE = NOW + timedelta(hours=1)


@pytest.fixture
def pipeline_client(tmp_path):
    app = create_app(Settings(_env_file=None, audit_log_path=tmp_path / "pipeline-audit.jsonl"))
    app.state.clock = lambda: NOW
    with TestClient(app) as client:
        yield client


def load_module_05():
    spec = importlib.util.spec_from_file_location("module_05_for_07_contract", MODULE_05)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load Module 05 integration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def route_query():
    return {
        "run_id": "00000000-0000-4000-8000-000000000705",
        "routes": [
            {
                "route_id": "contract-primary",
                "label": "Synthetic contract route",
                "travel_modes": ["CAR"],
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[100.0, 13.0], [100.2, 13.0]],
                },
                "segments": [
                    {
                        "start_index": 0,
                        "end_index": 1,
                        "enter_at": DEPARTURE.isoformat(),
                        "exit_at": (DEPARTURE + timedelta(minutes=40)).isoformat(),
                    }
                ],
            }
        ],
    }


def canonical_records(*, high_transport=False, omit_kind=None, omit_kinds=()):
    records = []
    for kind in (
        "current_weather",
        "weather_forecast",
        "transport_status",
        "closure",
        "disaster_event",
        "official_alert",
    ):
        if kind == omit_kind or kind in omit_kinds:
            continue
        high = high_transport and kind == "transport_status"
        records.append(
            {
                "schema_version": "canonical-record-v0.1-proposed",
                "record_id": f"contract-{kind}",
                "record_kind": kind,
                "status": "available",
                "source": {"name": "Synthetic contract provider", "authority": None},
                "source_lineage": f"https://example.org/contract/{kind}",
                "spatial_footprint": {"type": "Point", "coordinates": [100.1, 13.0]},
                "observed_at": (NOW - timedelta(minutes=10)).isoformat(),
                "valid_at": (DEPARTURE + timedelta(minutes=10)).isoformat(),
                "fetched_at": (NOW - timedelta(minutes=5)).isoformat(),
                "expires_at": (NOW + timedelta(hours=3)).isoformat(),
                "severity": "HIGH" if high else "LOW",
                "quality_flags": [],
                "value": {
                    "active": False,
                    "status": "CLOSED" if high else "NORMAL",
                    "severity": "HIGH" if high else "LOW",
                },
            }
        )
    return records


def evidence_record(kind, evidence_id):
    return Record(
        id=evidence_id,
        kind=kind,
        source_name="Synthetic cross-module fixture",
        url=f"https://example.org/contract/{kind}",
        observed_at=NOW - timedelta(minutes=10),
        fetched_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=3),
        excerpt="Synthetic contract evidence; not travel advice.",
    )


class PipelineState(SimpleNamespace):
    def records(self):
        found = []
        for result in (
            self.weather,
            self.transport,
            self.disasters,
            self.candidates,
            self.risk,
            self.knowledge,
            self.routes,
        ):
            if result:
                found.extend(result.records)
        return found


def pipeline_payload(*, upstream_ready, high_transport=False, omit_kind=None, omit_kinds=()):
    """upstream_ready: True/False pins 05's quality fields; None keeps what 05 computed."""
    integrated = load_module_05().build_context(
        route_query(),
        canonical_records(
            high_transport=high_transport, omit_kind=omit_kind, omit_kinds=omit_kinds
        ),
        now=NOW,
    )
    if omit_kind is None and not omit_kinds:
        assert all(
            status == "covered"
            for segment in integrated["routes"][0]["segments"]
            for status in segment["coverage"].values()
        )
        assert integrated["quality_flags"] == []

    if upstream_ready is True:
        integrated.update(confidence="HIGH", active_restriction=False)
    elif upstream_ready is False:
        integrated.pop("confidence", None)
        integrated.pop("active_restriction", None)
    risk_06 = assess_risk(integrated, now=NOW)
    routes_06 = analyze_routes(
        {
            "run_id": integrated["run_id"],
            "origin": [13.0, 100.0],
            "destination": [13.0, 100.2],
            "departure_time": DEPARTURE,
            "travel_modes": ["CAR"],
        },
        integrated,
        risk_06,
        now=NOW,
    )
    risk = RiskResult.model_validate(risk_06.model_dump(mode="python")).model_copy(
        update={"records": [evidence_record("risk", "contract-risk")]}
    )
    routes = RouteResult.model_validate(routes_06.model_dump(mode="python")).model_copy(
        update={"records": [evidence_record("route", "contract-route")]}
    )
    context = IntegratedContext.model_validate(integrated)
    state = PipelineState(
        run=SimpleNamespace(
            run_id=UUID(integrated["run_id"]),
            request=SimpleNamespace(departure_time=DEPARTURE, language="th"),
        ),
        context=context,
        weather=WeatherResult(
            summary="Synthetic complete weather check",
            records=[evidence_record("weather", "contract-weather")],
        ),
        transport=TransportResult(
            summary="Synthetic complete transport check",
            records=[evidence_record("transport", "contract-transport")],
        ),
        disasters=DisasterResult(
            alerts=[], records=[evidence_record("official", "contract-official")]
        ),
        candidates=SimpleNamespace(records=[]),
        risk=risk,
        knowledge=None,
        routes=routes,
    )
    return integrated, risk_06, build_decision_request(state)


def test_current_complete_coverage_stays_conservative_until_quality_is_confirmed(
    pipeline_client,
):
    integrated, risk, payload = pipeline_payload(upstream_ready=False)
    assert risk.level.value == "LOW"
    assert risk.confidence == 0.9
    assert integrated.get("confidence") is None
    assert integrated.get("active_restriction") is None
    assert payload["quality"]["confidence"] == "LOW"
    assert payload["quality"]["active_restriction"] is None

    result = pipeline_client.post("/v1/decisions", json=payload)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["risk_level"] == "LOW"
    assert body["action_code"] == "AVOID"
    assert {"low_confidence", "restriction_unknown"} <= set(body["escalation_reasons"])


def test_confirmed_complete_low_risk_reaches_normal_through_current_contract(
    pipeline_client,
):
    _, risk, payload = pipeline_payload(upstream_ready=True)
    assert risk.level.value == "LOW"
    assert payload["quality"]["confidence"] == "HIGH"
    assert payload["quality"]["active_restriction"] is False

    result = pipeline_client.post("/v1/decisions", json=payload)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["risk_level"] == "LOW"
    assert body["action_code"] == "NORMAL"
    assert body["confidence"] == 0.9
    assert not body["escalation_required"]


def test_high_risk_from_module_06_cannot_be_weakened_by_module_07(pipeline_client):
    _, risk, payload = pipeline_payload(upstream_ready=True, high_transport=True)
    assert risk.level.value == "HIGH"

    result = pipeline_client.post("/v1/decisions", json=payload)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["risk_level"] == "HIGH"
    assert body["action_code"] == "AVOID"
    assert body["rules_fired"] == ["HIGH_RISK"]
    assert body["emergency_assessment"]["status"] == "fallback"


def test_partial_coverage_from_module_05_cannot_select_a_safe_action(pipeline_client):
    # An essential kind (Contract Register issue #2); official_alert is now optional.
    integrated, risk, payload = pipeline_payload(upstream_ready=True, omit_kind="transport_status")
    coverage = integrated["routes"][0]["segments"][0]["coverage"]
    assert coverage["transport_status"] == "missing"
    assert {"missing", "partial"} <= set(integrated["quality_flags"])
    assert risk.level.value == "LOW"

    result = pipeline_client.post("/v1/decisions", json=payload)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["risk_level"] == "LOW"
    assert body["action_code"] == "AVOID"
    assert body["selected_route_id"] is None
    assert {"missing", "partial", "incomplete"} <= set(body["escalation_reasons"])


def test_kinds_module_04_can_produce_reach_normal_on_module_05_quality(pipeline_client):
    # No live provider publishes closure/official_alert. Keep 05's own confidence and
    # active_restriction (no override) so this exercises the real 05 -> 03 -> 07 wire.
    integrated, risk, payload = pipeline_payload(
        upstream_ready=None, omit_kinds=("closure", "official_alert")
    )
    coverage = integrated["routes"][0]["segments"][0]["coverage"]
    assert coverage["closure"] == coverage["official_alert"] == "missing"
    assert integrated["quality_flags"] == []
    assert integrated["confidence"] == "HIGH"
    assert integrated["active_restriction"] is False
    assert payload["quality"]["confidence"] == "HIGH"
    assert payload["quality"]["active_restriction"] is False

    result = pipeline_client.post("/v1/decisions", json=payload)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["risk_level"] == "LOW"
    assert body["action_code"] == "NORMAL"
    assert not body["escalation_required"]


def _flood_passage() -> dict:
    return {
        "document_id": "ddpm-flood-1",
        "authority": "Department of Disaster Prevention and Mitigation",
        "title": "Flood safety guide",
        "url": "https://example.org/contract/flood-guide",
        "language": "th-TH",
        "geography": ["*"],
        "hazard_types": ["GENERAL"],
        "effective_at": (NOW - timedelta(days=1)).isoformat(),
        "expires_at": (NOW + timedelta(days=1)).isoformat(),
        "page": 1,
        "section": "Evacuation",
        "text": "Synthetic contract passage; not travel advice.",
        "approved": True,
    }


def _contract_query() -> dict:
    return {
        "run_id": "contract-run",
        "origin": [13.0, 100.0],
        "destination": [13.0, 100.2],
        "departure_time": DEPARTURE.isoformat(),
        "language": "th-TH",
    }


def test_grounded_emergency_reachable_via_real_module_06_knowledge(tmp_path):
    """06's excerpt no longer embeds a per-query score, so 07 can verify a real
    retrieval result against a reviewed catalog entry by hash. Before that fix,
    "grounded" was structurally unreachable through the live 06 -> 07 wire: a
    catalog authored once against one alert wording would never match a live
    request phrased differently, because the embedded score differed too.
    """
    _, _, payload = pipeline_payload(upstream_ready=True, high_transport=True)
    passage = _flood_passage()

    # The reviewer authors the catalog once, against whatever alert wording 06
    # happened to retrieve with at review time.
    review_time_alert = {
        "hazard_id": "review-hazard",
        "hazard_type": "GENERAL",
        "severity": "HIGH",
        # Shares tokens with the passage text, unlike live_alert below: this and
        # live_alert deliberately produce different BM25 lexical scores.
        "title": "Flood safety advisory",
        "level": "AVOID",
        "active": True,
    }
    reviewed = retrieve_knowledge(_contract_query(), [review_time_alert], [passage], now=NOW)
    assert len(reviewed.records) == 1
    catalog_excerpt = reviewed.records[0].excerpt

    # The live request comes in with an unrelated, differently-worded alert for the
    # same passage. Only the excerpt's stability (not its content matching byte for
    # byte) is under test here.
    live_alert = {
        "hazard_id": "contract-hazard",
        "hazard_type": "GENERAL",
        "severity": "HIGH",
        # No shared tokens with the passage text or review_time_alert above.
        "title": "Storm bulletin update",
        "level": "AVOID",
        "active": True,
    }
    knowledge = retrieve_knowledge(_contract_query(), [live_alert], [passage], now=NOW)
    assert len(knowledge.records) == 1
    record = knowledge.records[0]
    # This is the property the fix guarantees: what gets reviewed and what gets
    # verified at request time are byte-identical for the same passage.
    assert record.excerpt == catalog_excerpt

    payload["evidence"].append(
        {
            "context": payload["context"],
            "evidence_id": "contract-knowledge",
            "kind": "knowledge",
            "source_name": record.source_name,
            "url": str(record.url),
            "official_source": record.official_source,
            "observed_at": record.observed_at.isoformat(),
            "fetched_at": record.fetched_at.isoformat(),
            "expires_at": record.expires_at.isoformat(),
            "excerpt": record.excerpt,
        }
    )

    catalog = EmergencyCatalog.load().content.model_dump(mode="json")
    catalog["version"] = "contract-test-v1"
    catalog["procedures"] = [
        {
            "procedure_id": "contract-procedure",
            "status": "reviewed",
            "region": "TH",
            "hazard": "GENERAL",
            "locale": "th-TH",
            "source_url": str(record.url),
            # Baked in once at review time, from catalog_excerpt, not from the live
            # request's own excerpt.
            "excerpt_sha256": hashlib.sha256(catalog_excerpt.encode()).hexdigest(),
            "reviewed_at": (NOW - timedelta(days=1)).isoformat(),
            "expires_at": (NOW + timedelta(hours=3)).isoformat(),
            "instructions": {
                "what_to_do_now": "SYNTHETIC: consult the test bulletin.",
                "safety_steps": ["SYNTHETIC: follow the test procedure."],
                "contacts": [],
                "nearest_support": [],
            },
        }
    ]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    app = create_app(
        Settings(
            _env_file=None,
            audit_log_path=tmp_path / "audit.jsonl",
            emergency_catalog_path=catalog_path,
        )
    )
    app.state.clock = lambda: NOW
    with TestClient(app) as client:
        response = client.post("/v1/decisions", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action_code"] == "AVOID"
    assert body["emergency_assessment"]["status"] == "grounded"
    assert body["emergency_assessment"]["evidence_ids"] == ["contract-knowledge"]
