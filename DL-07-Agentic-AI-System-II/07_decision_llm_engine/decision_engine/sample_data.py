"""Synthetic, time-relative fixtures. These are not provider data or real safety advice."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta


def scenarios(now: datetime | None = None) -> dict[str, dict]:
    now = now or datetime.now(UTC)
    context = {
        "request_id": "00000000-0000-4000-8000-000000000007",
        "route_id": "mock-primary",
        "departure_time": (now + timedelta(hours=2)).isoformat(),
    }
    base = {
        "context": context,
        "locale": "th-TH",
        "risk": {
            "context": context,
            "level": "LOW",
            "confidence": "HIGH",
            "model_version": "mock-risk-v1",
            "evidence_ids": ["mock-risk"],
        },
        "weather": {
            "context": context,
            "text": "Synthetic weather summary",
            "evidence_ids": ["mock-weather"],
        },
        "transport": {
            "context": context,
            "text": "Synthetic transport summary",
            "evidence_ids": ["mock-transport"],
        },
        "routes": {
            "context": context,
            "no_safe_route": False,
            "alternatives": [],
            "evidence_ids": ["mock-route"],
        },
        "quality": {
            "context": context,
            "confidence": "HIGH",
            "flags": [],
            "active_restriction": False,
            "data_version": "mock-data-v1",
        },
        "alerts": [],
        "evidence": [
            {
                "context": context,
                "evidence_id": f"mock-{kind}",
                "source_name": f"SYNTHETIC {kind} fixture",
                "url": f"https://example.org/mock/{kind}",
                "kind": kind,
                "official_source": kind == "official",
                "observed_at": (now - timedelta(minutes=10)).isoformat(),
                "fetched_at": (now - timedelta(minutes=5)).isoformat(),
                "expires_at": (now + timedelta(hours=1)).isoformat(),
                "excerpt": "MOCK DATA ONLY. Not an actual alert or travel assessment.",
            }
            for kind in ("risk", "weather", "transport", "route", "knowledge", "official", "time")
        ],
    }
    result = {"low_risk": deepcopy(base)}
    result["high_risk"] = deepcopy(base)
    result["high_risk"]["risk"]["level"] = "HIGH"
    result["closure"] = deepcopy(base)
    result["closure"]["alerts"] = [
        {
            "context": deepcopy(context),
            "level": "CLOSURE",
            "active": True,
            "evidence_ids": ["mock-official"],
        }
    ]
    result["closure"]["quality"]["active_restriction"] = True
    result["safer_route"] = deepcopy(base)
    result["safer_route"]["risk"]["level"] = "MEDIUM"
    result["safer_route"]["routes"]["alternatives"] = [
        {
            "route_id": "mock-alternative",
            "risk_level": "LOW",
            "usable": True,
            "clearly_safer": True,
            "evidence_ids": ["mock-route"],
        }
    ]
    result["safer_time"] = deepcopy(base)
    result["safer_time"]["risk"]["level"] = "MEDIUM"
    result["safer_time"]["time_assessment"] = {
        "context": deepcopy(context),
        "safer_later": True,
        "suggested_departure_time": (now + timedelta(hours=5)).isoformat(),
        "evidence_ids": ["mock-time"],
    }
    result["missing_data"] = deepcopy(base)
    result["missing_data"]["weather"] = None
    result["stale_data"] = deepcopy(base)
    result["stale_data"]["evidence"][0]["expires_at"] = now.isoformat()
    result["conflicting_data"] = deepcopy(base)
    result["conflicting_data"]["quality"]["flags"] = ["conflicting"]
    result["numeric_confidence"] = deepcopy(base)
    result["numeric_confidence"]["risk"]["confidence"] = 0.8
    result["numeric_confidence"]["quality"]["confidence"] = 0.75
    result["numeric_confidence"]["quality"]["schema_version"] = "07-draft-v2"
    result["emergency_fallback"] = deepcopy(result["high_risk"])
    result["emergency_fallback"]["emergency_context"] = {
        "context": deepcopy(context),
        "region": "TEST-REGION",
        "hazard": "TEST-HAZARD",
    }
    for flag in ("partial", "freshness_unknown"):
        result[flag] = deepcopy(base)
        result[flag]["quality"]["flags"] = [flag]
        result[flag]["quality"]["schema_version"] = "07-draft-v3"
    result["summary_only_risk"] = deepcopy(base)
    result["summary_only_risk"]["risk"]["level"] = "MEDIUM"
    result["summary_only_risk"]["risk"]["confidence"] = "LOW"
    result["partial_alternative"] = deepcopy(result["safer_route"])
    result["partial_alternative"]["routes"]["alternatives"][0]["clearly_safer"] = False
    result["partial_alternative"]["quality"]["flags"] = ["partial"]
    return result
