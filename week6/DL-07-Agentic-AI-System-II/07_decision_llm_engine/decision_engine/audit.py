import json
import threading
from pathlib import Path

from .models import DecisionResponse


class AuditUnavailable(RuntimeError):
    pass


class AuditStore:
    """Minimal JSONL prototype store; one API process, no raw input or free-form text."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def check(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock, self.path.open("a", encoding="utf-8"):
                pass
            return True
        except OSError:
            return False

    def append(self, result: DecisionResponse) -> None:
        entry = {
            "request_id": str(result.request_id),
            "evaluated_at": result.evaluated_at.isoformat(),
            "action_code": result.action_code,
            "rules_fired": result.rules_fired,
            "evidence_ids": [e.evidence_id for e in result.evidence_status],
            "evidence_validation": [e.model_dump() for e in result.evidence_status],
            "versions": result.versions.model_dump(),
            "confidence": result.confidence,
            "confidence_kind": result.confidence_kind,
            "confidence_details": result.confidence_details,
            "emergency_assessment": result.emergency_assessment.model_dump(),
            "escalation_reasons": result.escalation_reasons,
            "explanation_mode": result.explanation.mode,
            "validation_results": result.validation_results,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock, self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
                stream.flush()
        except OSError as error:
            raise AuditUnavailable("Cannot persist decision audit") from error
