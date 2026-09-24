"""Evidence helpers shared by the three Module 06 capabilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .models import Record, RecordKind


MODULE_SOURCE_URL = (
    "https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D/"
    "tree/develop/DL-07-Agentic-AI-System-II/06_risk_knowledge_services"
)


def module_record(
    kind: RecordKind,
    excerpt: str,
    *,
    now: datetime | None = None,
    ttl: timedelta = timedelta(minutes=15),
) -> Record:
    """Create provenance for a derived Module 06 result, not for an external fact."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    return Record(
        kind=kind,
        source_name="Module 06 deterministic assessment",
        url=MODULE_SOURCE_URL,
        official_source=False,
        observed_at=current,
        fetched_at=current,
        expires_at=current + ttl,
        excerpt=excerpt[:4000],
    )
