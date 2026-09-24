import sys
from datetime import UTC, datetime, timedelta

import pytest

from travel_agent.tools.base import ToolError
from travel_agent.tools.live import LiveToolSet
from travel_agent.tools.schemas import IntegratedContext, TravelQuery

NOW = datetime(2026, 9, 21, 3, 0, tzinfo=UTC)


def query() -> TravelQuery:
    return TravelQuery(
        run_id="run-live-1",
        origin=(13.7563, 100.5018),
        destination=(12.5684, 99.9577),
        departure_time=NOW + timedelta(minutes=10),
        travel_modes=["CAR"],
    )


def canonical(kind: str, record_id: str, *, severity: str = "MEDIUM") -> dict:
    return {
        "schema_version": "canonical-record-v0.1-proposed",
        "record_id": record_id,
        "record_kind": kind,
        "status": "available",
        "source": {"name": "Real provider", "authority": None},
        "source_lineage": "https://provider.example/events?id=1",
        "spatial_footprint": {"type": "Point", "coordinates": [100.25, 13.2]},
        "observed_at": NOW.isoformat(),
        "valid_at": None,
        "issued_at": None,
        "event_time": NOW.isoformat(),
        "fetched_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "severity": severity,
        "quality_flags": [],
        "value": {
            "event_type": "FL",
            "name": "Flood event",
            "description": "Provider-reported event",
            "starts_at": (NOW - timedelta(minutes=5)).isoformat(),
            "ends_at": (NOW + timedelta(minutes=30)).isoformat(),
        },
    }


def context_builder_spy(calls: list):
    def build(payload, records, *, now):
        calls.append((payload, records, now))
        return {
            "feature_schema_version": "integrated-travel-v0.1-proposed",
            "run_id": payload["run_id"],
            "created_at": now.isoformat(),
            "routes": payload["routes"],
            "evidence": records,
            "quality_flags": ["partial"],
            "degraded": True,
            "risk_score": None,
        }

    return build


@pytest.mark.asyncio
async def test_live_transport_and_disasters_feed_canonical_records_to_module_05():
    calls = []
    transport_record = canonical("transport_status", "tomtom:incident-1")
    disaster_record = canonical("disaster_event", "gdacs:FL:1:1", severity="HIGH")
    captured_transport = {}

    def fetch_transport(bbox, *, now, api_key):
        captured_transport.update(bbox=bbox, now=now, api_key=api_key)
        return [transport_record]

    tools = LiveToolSet(
        tomtom_api_key="test-key",
        clock=lambda: NOW,
        transport_fetcher=fetch_transport,
        disaster_fetcher=lambda *, now: [disaster_record],
        context_builder=context_builder_spy(calls),
    )

    transport = await tools.transport(query())
    disasters = await tools.disasters(query())
    routes = [
        {
            "route_id": "route-1",
            "label": "Route 1",
            "travel_modes": ["CAR"],
            "geometry": {
                "type": "LineString",
                "coordinates": [[100.5018, 13.7563], [99.9577, 12.5684]],
            },
            "segments": [
                {
                    "start_index": 0,
                    "end_index": 1,
                    "enter_at": (NOW + timedelta(minutes=10)).isoformat(),
                    "exit_at": (NOW + timedelta(hours=2)).isoformat(),
                }
            ],
        }
    ]
    context = await tools.integrate(query(), routes, None, transport, disasters)

    assert captured_transport == {
        "bbox": (99.9577, 12.5684, 100.5018, 13.7563),
        "now": NOW,
        "api_key": "test-key",
    }
    assert transport.records[0].source_name == "Real provider"
    assert disasters.alerts[0].severity.value == "HIGH"
    assert disasters.alerts[0].level == "CAUTION"
    assert disasters.alerts[0].active is True
    assert context.run_id == "run-live-1"
    assert calls[0][1] == [transport_record, disaster_record]


@pytest.mark.asyncio
async def test_successful_empty_provider_checks_have_non_synthetic_proof_records():
    tools = LiveToolSet(
        clock=lambda: NOW,
        transport_fetcher=lambda bbox, *, now, api_key: [],
        disaster_fetcher=lambda *, now: [],
        context_builder=context_builder_spy([]),
    )

    transport = await tools.transport(query())
    disasters = await tools.disasters(query())

    assert transport.canonical_records == []
    assert transport.records[0].source_name == "TomTom Orbis Traffic"
    assert "no matching active records" in transport.records[0].excerpt
    assert disasters.alerts == []
    assert "SYNTHETIC" not in disasters.records[0].source_name


@pytest.mark.asyncio
async def test_unavailable_provider_marks_tool_unavailable_instead_of_claiming_success():
    unavailable = {
        "status": "unavailable",
        "error_code": "PROVIDER_UNAVAILABLE",
    }
    tools = LiveToolSet(
        clock=lambda: NOW,
        transport_fetcher=lambda bbox, *, now, api_key: [unavailable],
        disaster_fetcher=lambda *, now: [],
        context_builder=context_builder_spy([]),
    )

    with pytest.raises(ToolError, match="PROVIDER_UNAVAILABLE"):
        await tools.transport(query())


@pytest.mark.asyncio
async def test_live_module_06_accepts_module_05_context_and_returns_agent_contracts():
    tools = LiveToolSet(
        clock=lambda: NOW,
        transport_fetcher=lambda bbox, *, now, api_key: [],
        disaster_fetcher=lambda *, now: [],
        context_builder=context_builder_spy([]),
    )
    integrated = IntegratedContext.model_validate(
        {
            "feature_schema_version": "integrated-travel-v0.1-proposed",
            "run_id": "run-live-1",
            "created_at": NOW.isoformat(),
            "routes": [
                {
                    "route_id": "route-1",
                    "label": "Route 1",
                    "travel_modes": ["CAR"],
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[100.5018, 13.7563], [99.9577, 12.5684]],
                    },
                    "segments": [
                        {
                            "start_index": 0,
                            "end_index": 1,
                            "enter_at": (NOW + timedelta(minutes=10)).isoformat(),
                            "exit_at": (NOW + timedelta(hours=2)).isoformat(),
                            "matched_record_ids": {},
                            "coverage": {"weather_observation": "missing"},
                        }
                    ],
                }
            ],
            "evidence": [],
            "quality_flags": ["missing"],
            "degraded": True,
            "risk_score": None,
        }
    )

    risk = await tools.risk(query(), integrated)
    knowledge = await tools.knowledge(query(), [])
    routes = await tools.routes(query(), integrated, risk)

    assert risk.model_version == "rule-baseline-v0.1.2"
    # 06 reports confidence as a number now (LOW/MEDIUM/HIGH map to 0.25/0.65/0.90).
    # This context carries no usable evidence, so it must stay in the lowest band.
    assert risk.confidence == pytest.approx(0.25)
    assert knowledge.records == []
    assert routes.primary.route_id == "route-1"
    assert routes.primary.clearly_safer is False


@pytest.mark.asyncio
async def test_live_integrate_includes_canonical_weather_records():
    calls = []
    weather_record = canonical("current_weather", "open-meteo:current:1")
    transport_record = canonical("transport_status", "tomtom:incident-1")
    disaster_record = canonical("disaster_event", "gdacs:FL:1:1")

    tools = LiveToolSet(
        clock=lambda: NOW,
        context_builder=context_builder_spy(calls),
    )

    from travel_agent.tools.schemas import DisasterResult, Record, TransportResult, WeatherResult

    rec = Record(
        kind="weather",
        source_name="Open-Meteo",
        url="https://open-meteo.com",
        official_source=False,
        observed_at=NOW,
        fetched_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        excerpt="Clear",
    )

    weather = WeatherResult(
        summary="Clear skies",
        records=[rec],
        canonical_records=[weather_record],
    )
    transport = TransportResult(
        summary="Normal traffic",
        records=[rec],
        canonical_records=[transport_record],
    )
    disasters = DisasterResult(
        alerts=[],
        records=[rec],
        canonical_records=[disaster_record],
    )

    routes = [
        {
            "route_id": "route-1",
            "label": "Route 1",
            "travel_modes": ["CAR"],
            "geometry": {
                "type": "LineString",
                "coordinates": [[100.5018, 13.7563], [99.9577, 12.5684]],
            },
            "segments": [
                {
                    "start_index": 0,
                    "end_index": 1,
                    "enter_at": (NOW + timedelta(minutes=10)).isoformat(),
                    "exit_at": (NOW + timedelta(hours=2)).isoformat(),
                }
            ],
        }
    ]

    context = await tools.integrate(query(), routes, weather, transport, disasters)

    assert context.run_id == "run-live-1"
    assert len(calls) == 1
    forwarded_records = calls[0][1]
    assert weather_record in forwarded_records
    assert transport_record in forwarded_records
    assert disaster_record in forwarded_records


@pytest.mark.asyncio
async def test_live_weather_produces_canonical_records():
    current_rec = canonical("current_weather", "open-meteo:current:test")
    forecast_rec = canonical("weather_forecast", "open-meteo:forecast:test")

    tools = LiveToolSet(
        clock=lambda: NOW,
        # Same (latitude, longitude) signature as Module 04's weather_service.
        current_weather_fetcher=lambda lat, lon: current_rec,
        forecast_fetcher=lambda lat, lon: [forecast_rec],
    )

    result = await tools.weather(query())
    # Origin and destination both fetched (1 current + 1 forecast each = 4 total)
    assert len(result.canonical_records) == 4
    assert result.canonical_records[0] == current_rec
    assert result.canonical_records[1] == forecast_rec
    assert result.summary != ""


@pytest.mark.asyncio
async def test_live_weather_calls_real_module_04_entry_points(monkeypatch):
    """Stubs cannot hide a signature mismatch: drive the real 04 functions offline."""
    from urllib.error import URLError

    from travel_agent.tools import live

    *_, fetch_current, fetch_forecast, _fetch_routes = live._dependencies()
    adapter = sys.modules["open_meteo_adapter"]

    def offline(*args, **kwargs):
        raise URLError("offline test")

    monkeypatch.setattr(adapter, "urlopen", offline)
    tools = LiveToolSet(
        clock=lambda: NOW,
        transport_fetcher=lambda bbox, *, now, api_key: [],
        disaster_fetcher=lambda *, now: [],
        context_builder=context_builder_spy([]),
        risk_knowledge_service=object(),
        current_weather_fetcher=fetch_current,
        forecast_fetcher=fetch_forecast,
    )

    # Real 04 turns the provider failure into explicit unavailable records, which the
    # agent reports as a weather tool failure; a TypeError would surface differently.
    with pytest.raises(ToolError) as caught:
        await tools.weather(query())
    assert caught.value.tool == "weather"
    assert caught.value.reason == "PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_live_weather_cites_a_bounded_subset_but_forwards_every_hour_to_05():
    # Open-Meteo returns 48 hourly forecasts per location; 07 accepts at most 64 evidence
    # items in total, so citing every hour would get the whole decision rejected.
    def hourly(lat, lon):
        records = []
        for hour in range(48):
            record = canonical("weather_forecast", f"open-meteo:{lat}:{hour}")
            record["spatial_footprint"] = {"type": "Point", "coordinates": [lon, lat]}
            record["valid_at"] = (NOW + timedelta(hours=hour)).isoformat()
            record["value"] = {"description": f"{lat} hour {hour}"}
            records.append(record)
        return records

    def current(lat, lon):
        record = canonical("current_weather", f"open-meteo:{lat}:now")
        record["spatial_footprint"] = {"type": "Point", "coordinates": [lon, lat]}
        record["value"] = {"description": f"{lat} current"}
        return record

    tools = LiveToolSet(
        clock=lambda: NOW,
        current_weather_fetcher=current,
        forecast_fetcher=hourly,
    )
    result = await tools.weather(query())

    assert len(result.canonical_records) == 2 + 2 * 48
    assert len(result.records) == 4
    # Departure is NOW+10min, so the first hour at or after it is NOW+1h.
    assert {record.excerpt for record in result.records} == {
        "13.7563 current",
        "13.7563 hour 1",
        "12.5684 current",
        "12.5684 hour 1",
    }


@pytest.mark.asyncio
async def test_live_route_candidates_uses_module_04_osrm_wrapper():
    captured = {}

    def fetch_routes(origin, destination, *, base_url):
        captured.update(origin=origin, destination=destination, base_url=base_url)
        return [
            {
                "route_id": "osrm-route-1",
                "label": None,
                "travel_modes": ["CAR"],
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[100.5018, 13.7563], [99.9577, 12.5684]],
                },
                "legs": [{"start_index": 0, "end_index": 1, "duration_minutes": 90, "mode": "CAR"}],
                "distance_km": 200.0,
            }
        ]

    tools = LiveToolSet(
        clock=lambda: NOW,
        osrm_base_url="https://osrm.example.org",
        route_fetcher=fetch_routes,
    )

    result = await tools.route_candidates(query())

    assert captured == {
        "origin": (13.7563, 100.5018),
        "destination": (12.5684, 99.9577),
        "base_url": "https://osrm.example.org",
    }
    assert len(result.candidates) == 1
    assert result.candidates[0].route_id == "osrm-route-1"
    assert result.records[0].source_name == "OSRM routing"
    assert result.records[0].kind == "route"


@pytest.mark.asyncio
async def test_live_route_candidates_calls_real_module_04_entry_point(monkeypatch):
    """Stubs cannot hide a signature mismatch: drive the real 04 function offline."""
    from urllib.error import URLError

    from travel_agent.tools import live

    *_, fetch_routes = live._dependencies()

    def offline(*args, **kwargs):
        raise URLError("offline test")

    # route_candidates.py is loaded via exec_module, not registered in sys.modules;
    # patch the function's own module globals instead.
    monkeypatch.setitem(fetch_routes.__globals__, "urlopen", offline)
    tools = LiveToolSet(
        clock=lambda: NOW,
        transport_fetcher=lambda bbox, *, now, api_key: [],
        disaster_fetcher=lambda *, now: [],
        context_builder=context_builder_spy([]),
        risk_knowledge_service=object(),
        current_weather_fetcher=lambda lat, lon: None,
        forecast_fetcher=lambda lat, lon: [],
        route_fetcher=fetch_routes,
    )

    with pytest.raises(ToolError) as caught:
        await tools.route_candidates(query())
    assert caught.value.tool == "route_candidates"
    assert "OSRM network error" in caught.value.reason


@pytest.mark.asyncio
async def test_live_transport_ongoing_incident_uses_fetched_at_for_freshness():
    """Ongoing incidents use fetched_at so long-term closures are not marked stale."""
    incident = canonical("transport_status", "tomtom:incident-ongoing")
    # Simulate a long-running closure from 2 years ago without lastReportTime
    incident["observed_at"] = None
    incident["event_time"] = (NOW - timedelta(days=700)).isoformat()
    incident["fetched_at"] = NOW.isoformat()
    incident["value"] = {
        "status": "CLOSED",
        "category": "roadClosed",
        "description": "Long-term closure",
        "time_validity": "present",
        "starts_at": (NOW - timedelta(days=700)).isoformat(),
    }

    tools = LiveToolSet(
        tomtom_api_key="test-key",
        clock=lambda: NOW,
        transport_fetcher=lambda bbox, *, now, api_key: [incident],
        disaster_fetcher=lambda *, now: [],
        context_builder=context_builder_spy([]),
    )

    transport = await tools.transport(query())
    assert len(transport.records) == 1
    # Must use NOW (fetched_at), not the 700-days-old event_time
    assert transport.records[0].observed_at == NOW


@pytest.mark.asyncio
async def test_live_transport_longdo_provider():
    captured = {}

    def fetch_longdo(bbox, *, now, api_key):
        captured.update(bbox=bbox, now=now, api_key=api_key)
        return []

    tools = LiveToolSet(
        transport_provider="longdo",
        longdo_api_key="longdo-secret-key",
        clock=lambda: NOW,
        transport_fetcher=fetch_longdo,
        disaster_fetcher=lambda *, now: [],
        context_builder=context_builder_spy([]),
    )

    transport = await tools.transport(query())
    assert captured == {
        "bbox": (99.9577, 12.5684, 100.5018, 13.7563),
        "now": NOW,
        "api_key": "longdo-secret-key",
    }
    assert transport.canonical_records == []
    assert transport.records[0].source_name == "Longdo Traffic (iTIC)"
    assert str(transport.records[0].url) == "https://event.longdo.com/feed/json"

