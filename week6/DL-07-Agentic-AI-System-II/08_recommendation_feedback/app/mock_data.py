"""
Mock RecommendationResponse fixtures — one per action_code, plus one
emergency scenario (AVOID_TRAVEL + emergency_instructions/official_contacts).
Lets 01_web_app build/test the UI before 06/07 are wired up.
"""

from datetime import datetime, timedelta, timezone

from app.schema import (
    ActionCode,
    ConfidenceLevel,
    DegradedService,
    EmergencyContact,
    RecommendationResponse,
    RiskLevel,
    RouteOption,
    ServiceStatus,
    SourceCitation,
    SourceType,
    Waypoint,
)

_NOW = datetime.now(timezone.utc)


def _times(offset_min: int = 0, ttl_min: int = 30):
    observed = _NOW - timedelta(minutes=offset_min)
    fetched = _NOW
    expires = _NOW + timedelta(minutes=ttl_min)
    return observed, fetched, expires


TRAVEL_NORMALLY = RecommendationResponse(
    request_id="mock-req-001",
    action_code=ActionCode.TRAVEL_NORMALLY,
    risk_level=RiskLevel.LOW,
    confidence=0.94,
    confidence_level=ConfidenceLevel.HIGH,
    short_summary="Conditions along your route are normal. No active restrictions.",
    immediate_actions=["Proceed as planned."],
    primary_route=RouteOption(
        route_id="r-001",
        description="Sukhumvit Rd -> BTS Asok -> destination",
        mode="transit",
        estimated_duration_min=35,
        risk_level=RiskLevel.LOW,
        trade_offs=[],
        waypoints=[
            Waypoint(lat=13.7563, lng=100.5018, label="Start: Sukhumvit"),
            Waypoint(lat=13.7367, lng=100.5602, label="BTS Asok"),
        ],
    ),
    alternative_routes=[],
    emergency_instructions=[],
    official_contacts=[],
    reasons=["No active weather alerts.", "Transit systems operating on schedule."],
    sources=[
        SourceCitation(name="TMD Weather Feed", source_type=SourceType.WEATHER),
        SourceCitation(name="BTS Service Status", source_type=SourceType.TRANSPORT),
    ],
    observed_at=_times()[0],
    fetched_at=_times()[1],
    expires_at=_times()[2],
    limitations=[],
    degraded_services=[],
)

CHANGE_ROUTE = RecommendationResponse(
    request_id="mock-req-002",
    action_code=ActionCode.CHANGE_ROUTE,
    risk_level=RiskLevel.MEDIUM,
    confidence=0.81,
    confidence_level=ConfidenceLevel.HIGH,
    short_summary="Your planned route passes a flooded underpass. A safer route is available.",
    immediate_actions=["Switch to the alternative route below before departing."],
    primary_route=RouteOption(
        route_id="r-010",
        description="Original route via Rama IV underpass",
        mode="car",
        estimated_duration_min=25,
        risk_level=RiskLevel.MEDIUM,
        trade_offs=["Underpass flooding reported in last hour"],
        waypoints=[
            Waypoint(lat=13.7280, lng=100.5340, label="Rama IV underpass"),
        ],
    ),
    alternative_routes=[
        RouteOption(
            route_id="r-011",
            description="Detour via Rama IV surface road",
            mode="car",
            estimated_duration_min=38,
            risk_level=RiskLevel.LOW,
            trade_offs=["+13 min", "Avoids flood zone"],
            waypoints=[
                Waypoint(lat=13.7295, lng=100.5365, label="Surface road detour"),
            ],
        )
    ],
    emergency_instructions=[],
    official_contacts=[],
    reasons=["Municipal flood sensor reported water level above threshold 40 min ago."],
    sources=[
        SourceCitation(name="BMA Flood Monitoring", source_type=SourceType.DISASTER_RAG),
        SourceCitation(name="Route Risk Model v2", source_type=SourceType.ROUTE_MODEL),
    ],
    observed_at=_times(40)[0],
    fetched_at=_times(40)[1],
    expires_at=_times(40, 20)[2],
    limitations=["Flood sensor data refreshes every 15 minutes."],
    degraded_services=[],
)

DELAY_TRAVEL = RecommendationResponse(
    request_id="mock-req-003",
    action_code=ActionCode.DELAY_TRAVEL,
    risk_level=RiskLevel.MEDIUM,
    # Deliberately mirrors what 03_travel_ai_agent forwards TODAY: 07 only
    # emits a categorical level, so the numeric field arrives as null.
    confidence=None,
    confidence_level=ConfidenceLevel.MEDIUM,
    short_summary="A severe thunderstorm is expected to pass within 90 minutes.",
    immediate_actions=["Delay departure by approximately 90 minutes if possible."],
    primary_route=None,
    alternative_routes=[],
    emergency_instructions=[],
    official_contacts=[],
    reasons=["TMD storm cell tracking shows path over your route.", "Risk is time-dependent and expected to clear."],
    sources=[SourceCitation(name="TMD Storm Tracker", source_type=SourceType.WEATHER)],
    observed_at=_times(10)[0],
    fetched_at=_times(10)[1],
    expires_at=_times(10, 90)[2],
    limitations=["Storm path forecasts carry inherent uncertainty."],
    degraded_services=[],
)

AVOID_TRAVEL = RecommendationResponse(
    request_id="mock-req-004",
    action_code=ActionCode.AVOID_TRAVEL,
    risk_level=RiskLevel.HIGH,
    confidence=0.88,
    confidence_level=ConfidenceLevel.HIGH,
    short_summary="Official closure on your route with no acceptable alternative right now.",
    immediate_actions=["Do not travel until the closure is lifted.", "Check back in 1 hour."],
    primary_route=RouteOption(
        route_id="r-020",
        description="Route via closed bridge",
        mode="car",
        estimated_duration_min=None,
        risk_level=RiskLevel.HIGH,
        trade_offs=["Bridge closed by official order"],
        waypoints=[Waypoint(lat=13.7100, lng=100.4900, label="Closed bridge")],
    ),
    alternative_routes=[],
    emergency_instructions=[],
    official_contacts=[],
    reasons=["Department of Highways closure order active since 2 hours ago.", "No alternative route within acceptable detour distance."],
    sources=[SourceCitation(name="DOH Closure Bulletin", source_type=SourceType.OFFICIAL)],
    observed_at=_times(120)[0],
    fetched_at=_times(120)[1],
    expires_at=_times(120, 60)[2],
    limitations=[],
    degraded_services=[DegradedService(service_name="alt_route_finder", status=ServiceStatus.DEGRADED, detail="Limited detour options near closure zone.")],
)

EMERGENCY_INSTRUCTIONS = RecommendationResponse(
    request_id="mock-req-005",
    # Emergency guidance rides on one of the four shared action codes.
    action_code=ActionCode.AVOID_TRAVEL,
    risk_level=RiskLevel.HIGH,
    confidence=0.97,
    confidence_level=ConfidenceLevel.HIGH,
    short_summary="Active earthquake alert issued for your current area.",
    immediate_actions=["Move away from windows and heavy furniture now.", "Do not use elevators."],
    primary_route=None,
    alternative_routes=[],
    emergency_instructions=[
        "Drop, cover, and hold on if shaking continues.",
        "After shaking stops, evacuate to the nearest open area.",
        "Follow instructions from local authorities.",
    ],
    official_contacts=[
        EmergencyContact(
            name="Thailand Emergency Hotline",
            phone="191",
            contact_type="police",
            region="TH",
            effective_date=_NOW - timedelta(days=30),
        ),
        EmergencyContact(
            name="Erawan Medical Emergency Center",
            phone="1669",
            contact_type="hospital",
            region="TH",
            effective_date=_NOW - timedelta(days=30),
        ),
    ],
    reasons=["Seismic sensor network detected M5.8+ event within 20km."],
    sources=[SourceCitation(name="National Disaster Warning Center", source_type=SourceType.OFFICIAL)],
    observed_at=_times(2)[0],
    fetched_at=_times(2)[1],
    expires_at=_times(2, 15)[2],
    limitations=["Aftershock risk not yet quantified."],
    degraded_services=[],
)

ALL_SCENARIOS = {
    "travel_normally": TRAVEL_NORMALLY,
    "change_route": CHANGE_ROUTE,
    "delay_travel": DELAY_TRAVEL,
    "avoid_travel": AVOID_TRAVEL,
    "emergency_instructions": EMERGENCY_INSTRUCTIONS,
}
