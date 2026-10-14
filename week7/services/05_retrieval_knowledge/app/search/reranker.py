"""Optional cross-encoder reranking (week4 src/rerankers.py). Off unless RERANK_MODEL is set."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.core.logging import get_logger

log = get_logger(__name__)


class Reranker(Protocol):
    def score(self, query: str, texts: Sequence[str]) -> list[float]: ...


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        pairs = [(query, text) for text in texts]
        return [float(s) for s in self._model.predict(pairs, show_progress_bar=False)]


def load_reranker(model_name: str) -> Reranker | None:
    """None when switched off or when the model cannot be loaded; search works without it."""
    if not model_name:
        return None
    try:
        return CrossEncoderReranker(model_name)
    except Exception as exc:
        log.warning("reranker_unavailable", model=model_name, error_type=type(exc).__name__)
        return None
