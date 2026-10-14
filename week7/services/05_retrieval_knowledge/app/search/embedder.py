"""Sentence embeddings for the vector side of the search (multilingual MiniLM, week4)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    model_name: str
    dimension: int

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """float32 array of shape (len(texts), dimension), each row of length 1."""
        ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        # Imported here: torch is heavy, and tests that use a fake never load it.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.dimension = int(self._model.get_embedding_dimension())

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        vectors = self._model.encode(
            list(texts),
            batch_size=64,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)
