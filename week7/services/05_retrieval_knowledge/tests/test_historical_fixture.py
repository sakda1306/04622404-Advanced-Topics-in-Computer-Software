"""eval/fixtures/historical_docs.json.gz: 07's archive, valid for /index/upsert (CONTRACT v1.13)."""

from __future__ import annotations

import dataclasses
from collections import Counter

from app.schemas.index import DocumentIn
from scripts.eval_retrieval import EVAL_DIR
from scripts.eval_thai import load_historical_documents


def test_every_archive_document_is_a_valid_upsert() -> None:
    documents = load_historical_documents(EVAL_DIR)
    assert len({d.doc_id for d in documents}) == len(documents)
    for document in documents:
        DocumentIn(**{**dataclasses.asdict(document), "team_ids": list(document.team_ids)})
        assert "## Sources and license" in document.text, document.doc_id


def test_archive_covers_every_past_season() -> None:
    documents = load_historical_documents(EVAL_DIR)
    topics = Counter(d.topic for d in documents)
    assert topics["season_table"] == 34
    assert topics["team_season"] == 686
    assert topics["head_to_head"] > 900
    assert topics["club_record"] == 51
    assert topics["league_records"] == 1
    assert all(d.season is None for d in documents if d.topic in ("club_record", "league_records"))
    seasons = {d.season for d in documents if d.topic == "season_table"}
    assert seasons == {str(year) for year in range(1992, 2026)}
