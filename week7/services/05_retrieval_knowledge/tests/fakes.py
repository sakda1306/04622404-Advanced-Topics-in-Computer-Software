"""Stand-ins for the embedding model and the reranker: deterministic, no download."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Sequence

import numpy as np

from app.search.tokenize import tokenize


class FakeEmbedder:
    """Bag-of-words vectors: texts sharing words point the same way."""

    def __init__(self, model_name: str = "fake-embedder", dimension: int = 64) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.calls: list[list[str]] = []
        self.fail = False

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if self.fail:
            raise RuntimeError("embedding model crashed")
        self.calls.append(list(texts))
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                bucket = int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dimension
                vectors[row, bucket] += 1.0
            norm = float(np.linalg.norm(vectors[row]))
            if norm:
                vectors[row] /= norm
        return vectors


class GatedEmbedder(FakeEmbedder):
    """Stops inside the next encode() until released: shows what happens mid-embedding."""

    def __init__(self) -> None:
        super().__init__()
        self.hold_next = False
        self.entered = threading.Event()
        self.release = threading.Event()

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if self.hold_next:
            self.hold_next = False
            self.entered.set()
            self.release.wait(timeout=10)
        return super().encode(texts)


class FakeReranker:
    """Scores 1.0 for texts that contain `prefer`, 0.0 otherwise."""

    def __init__(self, prefer: str) -> None:
        self.prefer = prefer

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        return [1.0 if self.prefer in text else 0.0 for text in texts]


class FailingReranker:
    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        raise RuntimeError("reranker crashed")
