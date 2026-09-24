"""Turn Module 04's route candidates into the timed routes Module 05 needs.

04 knows how long each leg takes; Module 02 gives the agent the departure time, so the
agent is the one that can say when the traveller enters and leaves each stretch. The
arithmetic is plain cumulative addition: no estimate is invented here.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from travel_agent.tools.schemas import RouteCandidate


def timed_routes(
    candidates: list[RouteCandidate], departure_time: datetime
) -> list[dict[str, Any]]:
    routes = []
    for candidate in candidates:
        enter_at = departure_time
        segments = []
        for leg in candidate.legs:
            exit_at = enter_at + timedelta(minutes=leg.duration_minutes)
            segments.append(
                {
                    "start_index": leg.start_index,
                    "end_index": leg.end_index,
                    "enter_at": enter_at.isoformat(),
                    "exit_at": exit_at.isoformat(),
                }
            )
            enter_at = exit_at
        routes.append(
            {
                "route_id": candidate.route_id,
                "label": candidate.label,
                "travel_modes": candidate.travel_modes,
                "geometry": candidate.geometry,
                "segments": segments,
            }
        )
    return routes
