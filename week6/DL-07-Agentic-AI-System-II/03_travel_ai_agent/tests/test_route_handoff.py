"""04 -> 03 -> 05 -> 06: candidate routes, their ETAs, and the untouched context."""

from datetime import UTC, datetime, timedelta

import pytest

from travel_agent.routes import timed_routes
from travel_agent.tools.mocks import MockToolSet
from travel_agent.tools.schemas import IntegratedContext, RouteCandidate, RouteLeg, TravelQuery

from .conftest import run_body

DEPARTURE = datetime(2026, 9, 21, 2, 0, tzinfo=UTC)


def candidate(**overrides) -> RouteCandidate:
    values = {
        "route_id": "r1",
        "geometry": {
            "type": "LineString",
            "coordinates": [[100.5, 13.7], [100.2, 13.1], [99.9, 12.5]],
        },
        "legs": [
            RouteLeg(start_index=0, end_index=1, duration_minutes=30),
            RouteLeg(start_index=1, end_index=2, duration_minutes=90),
        ],
    }
    return RouteCandidate(**(values | overrides))


def test_segments_run_from_the_departure_time_without_gaps():
    [route] = timed_routes([candidate()], DEPARTURE)

    assert [(s["start_index"], s["end_index"]) for s in route["segments"]] == [(0, 1), (1, 2)]
    first, second = route["segments"]
    assert first["enter_at"] == DEPARTURE.isoformat()
    assert first["exit_at"] == (DEPARTURE + timedelta(minutes=30)).isoformat()
    # The next stretch starts exactly where the previous one ended: Module 05 matches
    # evidence by these windows, so a gap would silently drop evidence.
    assert second["enter_at"] == first["exit_at"]
    assert second["exit_at"] == (DEPARTURE + timedelta(minutes=120)).isoformat()


def test_route_candidate_legs_must_cover_the_whole_line():
    with pytest.raises(ValueError):
        candidate(legs=[RouteLeg(start_index=0, end_index=1, duration_minutes=30)])


async def test_agent_forwards_module_05_context_to_06_unchanged(make_client):
    seen = {}

    class Recording(MockToolSet):
        async def risk(self, query, context):
            seen["context"] = context
            return await super().risk(query, context)

    result = (await make_client(tools=Recording()).post("/v1/agent/runs", json=run_body())).json()

    context = seen["context"]
    assert isinstance(context, IntegratedContext)
    assert context.feature_schema_version == "integrated-travel-v0.1-proposed"
    # The detail 06 scores on must survive: routes, segments and coverage.
    segments = context.routes[0]["segments"]
    assert segments[0]["enter_at"] and segments[0]["coverage"]
    assert result["status"] == "completed"


async def test_additive_fields_from_05_are_not_dropped():
    context = IntegratedContext.model_validate(
        {
            "feature_schema_version": "integrated-travel-v0.1-proposed",
            "routes": [{"route_id": "r1", "segments": []}],
            "quality_flags": ["partial", "made_up_flag"],
            "degraded": True,
            "future_field": {"kept": True},
        }
    )
    assert context.resolved_primary_route_id == "r1"
    assert context.model_dump()["future_field"] == {"kept": True}


async def test_unknown_coverage_words_do_not_reach_module_07(make_client):
    class Odd(MockToolSet):
        async def integrate(self, query, routes, weather, transport, disasters):
            base = await super().integrate(query, routes, weather, transport, disasters)
            return base.model_copy(
                update={"quality_flags": ["partial", "freshness_unknown", "coverage_tbd"]}
            )

    result = (await make_client(tools=Odd()).post("/v1/agent/runs", json=run_body())).json()
    # "coverage_tbd" would make 07 answer 422, which the agent reports as
    # DECISION_UNAVAILABLE; getting a recommendation shows the word was dropped.
    assert result["status"] == "completed"
    # partial/freshness_unknown did reach 07: its v3 policy escalates on them even
    # when the risk is LOW, so incomplete coverage cannot read as "safe to travel".
    assert result["recommendation"]["type"] == "AVOID_TRAVEL"


async def test_missing_route_candidates_degrade_instead_of_failing(make_client):
    class NoRoutes(MockToolSet):
        async def route_candidates(self, query: TravelQuery):
            raise RuntimeError("provider down")

    result = (await make_client(tools=NoRoutes()).post("/v1/agent/runs", json=run_body())).json()
    assert result["status"] == "partial_result"
    assert result["service_status"]["route_candidates"] == "unavailable"
    # 06's own route analysis still ran, so its key must not be marked down with it.
    assert result["service_status"]["route"] == "ok"
