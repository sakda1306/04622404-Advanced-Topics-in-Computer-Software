"""Job progress shown to users (docs/02_api_spec.md sections 6.1 and 6.3).

Messages come from the backend in the request language; the Agent's own progress
text is not shown because it is untrusted and may be in another language.
"""

from __future__ import annotations

from app.domain.enums import JobStage
from app.infrastructure.redis.job_state import TERMINAL_EVENTS

__all__ = ["STAGE_PROGRESS", "TERMINAL_EVENTS", "stage_message"]

STAGE_PROGRESS = {
    JobStage.QUEUED: 0,
    JobStage.FETCHING_DATA: 20,
    JobStage.ASSESSING_RISK: 60,
    JobStage.GENERATING_ADVICE: 90,
    JobStage.COMPLETED: 100,
    JobStage.FAILED: 100,
    JobStage.CANCELLED: 100,
}

_MESSAGES = {
    "en": {
        JobStage.QUEUED: "Waiting to start",
        JobStage.FETCHING_DATA: "Checking weather, transport and disaster alerts",
        JobStage.ASSESSING_RISK: "Assessing the risk",
        JobStage.GENERATING_ADVICE: "Writing the recommendation",
        JobStage.COMPLETED: "Done",
        JobStage.FAILED: "The request could not be completed",
        JobStage.CANCELLED: "Cancelled",
    },
    "th": {
        JobStage.QUEUED: "รอเริ่มประมวลผล",
        JobStage.FETCHING_DATA: "กำลังตรวจสอบสภาพอากาศ การเดินทาง และประกาศภัยพิบัติ",
        JobStage.ASSESSING_RISK: "กำลังประเมินความเสี่ยง",
        JobStage.GENERATING_ADVICE: "กำลังเขียนคำแนะนำ",
        JobStage.COMPLETED: "เสร็จแล้ว",
        JobStage.FAILED: "ไม่สามารถดำเนินการตามคำขอได้",
        JobStage.CANCELLED: "ยกเลิกแล้ว",
    },
}


def stage_message(stage: JobStage, language: str) -> str:
    return _MESSAGES.get(language, _MESSAGES["en"])[stage]
