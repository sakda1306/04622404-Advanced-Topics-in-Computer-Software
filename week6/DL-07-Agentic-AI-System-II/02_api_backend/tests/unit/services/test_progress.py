from __future__ import annotations

import pytest

from app.domain.enums import JobStage
from app.services.progress import STAGE_PROGRESS, TERMINAL_EVENTS, stage_message


def test_progress_grows_with_each_stage() -> None:
    order = [
        JobStage.QUEUED,
        JobStage.FETCHING_DATA,
        JobStage.ASSESSING_RISK,
        JobStage.GENERATING_ADVICE,
        JobStage.COMPLETED,
    ]

    values = [STAGE_PROGRESS[stage] for stage in order]

    assert values == sorted(values)
    assert values[0] == 0
    assert values[-1] == 100


@pytest.mark.parametrize("stage", list(JobStage))
@pytest.mark.parametrize("language", ["th", "en"])
def test_every_stage_has_a_message(stage: JobStage, language: str) -> None:
    assert stage_message(stage, language)


def test_messages_follow_the_language() -> None:
    assert stage_message(JobStage.ASSESSING_RISK, "th") == "กำลังประเมินความเสี่ยง"
    assert stage_message(JobStage.ASSESSING_RISK, "ja") == "Assessing the risk"


def test_terminal_events() -> None:
    assert frozenset({"completed", "failed", "cancelled"}) == TERMINAL_EVENTS
