"""hit@1 and hit@3 on the Thai golden set (Design.md §6: hit@3 below 0.8 means change the model).

Downloads and runs the real embedding model. Not a pytest test.
Run from `api/`: python -m tests.rag.eval_golden [model name]
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.rag.embedder import SentenceTransformerEmbedder
from app.rag.index import RagIndex

GOLDEN = Path(__file__).with_name("golden_th.jsonl")
DATA = Path(__file__).parents[3] / "data"
DEFAULT_MODEL = "intfloat/multilingual-e5-base"


def evaluate(model_name: str) -> None:
    cases = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines()]
    embedder = SentenceTransformerEmbedder(model_name)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        index = RagIndex(data_dir=str(DATA), db_path=f"{folder}/rag.db", embedder=embedder)
        index.build()
        print(f"model: {model_name}, cases: {len(cases)}")
        for mode in ("hybrid", "vector", "bm25"):
            hit_1 = hit_3 = 0
            for case in cases:
                found = [h.chunk.chunk_id for h in index.search(case["query"], top_k=3, mode=mode)]
                in_1 = bool(set(found[:1]) & set(case["expected"]))
                in_3 = bool(set(found) & set(case["expected"]))
                hit_1 += in_1
                hit_3 += in_3
                if mode == "hybrid" and not in_3:
                    print(f"MISS {case['query']}  want {case['expected'][0]}, got {found}")
            print(f"{mode}: hit@1 {hit_1 / len(cases):.2f}, hit@3 {hit_3 / len(cases):.2f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    evaluate(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL)
