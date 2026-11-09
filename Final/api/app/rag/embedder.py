"""Sentence embeddings for the vector side of the search (Design.md §6)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

import numpy as np


class Embedder(Protocol):
    model_name: str
    dimension: int

    def encode_passages(self, texts: Sequence[str]) -> np.ndarray:
        """float32 array of shape (len(texts), dimension), each row of length 1."""
        ...

    def encode_query(self, text: str) -> np.ndarray:
        """float32 array of shape (dimension,), of length 1."""
        ...


def prefixed(model_name: str, texts: Sequence[str], kind: Literal["query", "passage"]) -> list[str]:
    """E5 models are trained with these prefixes and score worse without them."""
    if "e5" not in model_name.lower():
        return list(texts)
    return [f"{kind}: {text}" for text in texts]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        # Imported here: torch is heavy, and tests that use a fake never load it.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.dimension = int(self._model.get_embedding_dimension() or 0)

    def _encode(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def encode_passages(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return self._encode(prefixed(self.model_name, texts, "passage"))

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode(prefixed(self.model_name, [text], "query"))[0]
