"""Filtered local disaster-knowledge retrieval.

This is the deterministic retrieval layer. Embedding/vector backends can replace the
text scorer later without weakening authority, geography, or validity filters.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Iterable

from .hashing import content_sha256
from .models import (
    AlertInput,
    KnowledgePassage,
    KnowledgeResult,
    Record,
    TravelQuery,
    as_mapping,
)


TOKEN_RE = re.compile(r"[\w\u0E00-\u0E7F]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text) if len(token) > 1]


def _bm25_scores(query: list[str], documents: list[list[str]]) -> list[float]:
    if not query or not documents:
        return [0.0] * len(documents)
    count = len(documents)
    average_length = sum(len(document) for document in documents) / count or 1.0
    frequencies = Counter(token for document in documents for token in set(document))
    scores: list[float] = []
    for document in documents:
        terms = Counter(document)
        score = 0.0
        for token in set(query):
            tf = terms[token]
            if not tf:
                continue
            inverse = math.log(1 + (count - frequencies[token] + 0.5) / (frequencies[token] + 0.5))
            denominator = tf + 1.2 * (1 - 0.75 + 0.75 * len(document) / average_length)
            score += inverse * (tf * 2.2) / denominator
        scores.append(score)
    maximum = max(scores, default=0.0)
    return [score / maximum if maximum else 0.0 for score in scores]


def _language_matches(requested: str, available: str) -> bool:
    requested_root = requested.casefold().split("-")[0]
    available_root = available.casefold().split("-")[0]
    return available_root in {requested_root, "multi", "multilingual", "*"}


def _alert_inputs(alerts: Iterable[Any]) -> list[AlertInput]:
    return [AlertInput.model_validate(as_mapping(alert)) for alert in alerts]


def retrieve_knowledge(
    query: TravelQuery | dict[str, Any],
    alerts: Iterable[AlertInput | dict[str, Any]],
    passages: Iterable[KnowledgePassage | dict[str, Any]],
    *,
    now: datetime | None = None,
    top_k: int = 5,
    minimum_score: float = 0.20,
) -> KnowledgeResult:
    """Retrieve only approved, current, location-appropriate passages.

    An empty result explicitly means that sufficiently grounded evidence was not
    found. No generic emergency procedure is fabricated as a fallback.
    """

    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20")
    if not 0 <= minimum_score <= 1:
        raise ValueError("minimum_score must be between 0 and 1")
    parsed_query = TravelQuery.model_validate(as_mapping(query))
    parsed_alerts = _alert_inputs(alerts)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    active_alerts = [alert for alert in parsed_alerts if alert.active]
    if not active_alerts:
        return KnowledgeResult()

    hazards = {alert.hazard_type.casefold() for alert in active_alerts}
    query_text = " ".join(
        [
            *hazards,
            *(alert.title for alert in active_alerts),
            *(alert.level for alert in active_alerts),
        ]
    )
    query_tokens = _tokens(query_text)
    candidates: list[KnowledgePassage] = []
    for raw in passages:
        passage = raw if isinstance(raw, KnowledgePassage) else KnowledgePassage.model_validate(raw)
        geography = {item.casefold() for item in passage.geography}
        passage_hazards = {item.casefold() for item in passage.hazard_types}
        if not passage.approved or not passage.effective_at <= current < passage.expires_at:
            continue
        if not _language_matches(parsed_query.language, passage.language):
            continue
        wrong_geography = (
            parsed_query.geography
            and "*" not in geography
            and parsed_query.geography.casefold() not in geography
        )
        if wrong_geography:
            continue
        if passage_hazards and not hazards.intersection(passage_hazards):
            continue
        candidates.append(passage)

    document_tokens = [_tokens(f"{item.title} {item.section} {item.text}") for item in candidates]
    lexical_scores = _bm25_scores(query_tokens, document_tokens)
    ranked: list[tuple[float, KnowledgePassage]] = []
    for passage, lexical in zip(candidates, lexical_scores, strict=True):
        passage_hazards = {item.casefold() for item in passage.hazard_types}
        hazard_bonus = 0.30 if hazards.intersection(passage_hazards) else 0.0
        authority_bonus = 0.10 if passage.authority else 0.0
        score = min(1.0, lexical * 0.60 + hazard_bonus + authority_bonus)
        if score >= minimum_score:
            ranked.append((score, passage))
    ranked.sort(key=lambda item: (-item[0], item[1].document_id, item[1].section))

    records: list[Record] = []
    for _score, passage in ranked[:top_k]:
        location = f"page={passage.page}" if passage.page is not None else "page=unknown"
        # Stable citation only: no per-query ranking score. Module 07's emergency
        # catalog matches a procedure to evidence by hashing this excerpt verbatim
        # against a reviewed value; a score that changes with every query wording
        # would make that hash never match, so "grounded" guidance could never fire
        # even when a reviewed procedure genuinely covers this passage.
        excerpt = (
            f"[document_id={passage.document_id}; {location}; section={passage.section}] "
            f"{passage.text}"
        )
        records.append(Record(
            kind="knowledge",
            source_name=passage.authority,
            url=passage.url,
            official_source=True,
            observed_at=passage.effective_at,
            fetched_at=current,
            expires_at=passage.expires_at,
            excerpt=excerpt,
            # Identity of the content itself, so a change to the line above cannot
            # invalidate a reviewed procedure, and edited source text is detected.
            content_sha256=content_sha256(passage.text),
        ))
    return KnowledgeResult(records=records)
