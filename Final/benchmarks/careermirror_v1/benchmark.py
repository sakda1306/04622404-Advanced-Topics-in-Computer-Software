"""Validate frozen cases, score predictions, or run the production retriever.

Run from any directory. Validation and prediction scoring use the standard library.
Retrieval needs the API dependencies; vector/hybrid also load the embedding model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "api"))


def fingerprint(path: Path) -> str:
    """Hash content only: git may check text out with either line ending on any machine."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate(directory: Path = HERE) -> list[dict]:
    from app.rag.chunking import load_chunks

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    path = directory / "golden_th.jsonl"
    if fingerprint(path) != manifest["dataset_sha256"]:
        raise ValueError("Dataset fingerprint changed; review and version the dataset")
    for name, digest in manifest["source_sha256"].items():
        if fingerprint(REPO / name) != digest:
            raise ValueError(f"Source drift: {name}; review labels before benchmarking")
    cases = read_jsonl(path)
    chunks = {c.chunk_id for c in load_chunks(str(REPO / "data"))}
    count = manifest["case_count"]
    if len(cases) != count or len({c["id"] for c in cases}) != count:
        raise ValueError(f"Expected exactly {count} unique cases")
    if len({c["query"] for c in cases}) != count:
        raise ValueError("Duplicate queries")
    if dict(Counter(c["category"] for c in cases)) != manifest["category_counts"]:
        raise ValueError("Category counts disagree with manifest")
    for case in cases:
        if (
            not case["reference_answer_th"]
            or not case["source_refs"]
            or not case["criteria"]
        ):
            raise ValueError(f"Missing reference or rubric: {case['id']}")
        if not set(case["expected"]) <= chunks:
            raise ValueError(f"Unknown chunk: {case['id']}")
        if bool(case["expected"]) == bool(case["expected_route"]):
            raise ValueError(f"Case must target retrieval or routing: {case['id']}")
        if any(not (REPO / ref).is_file() for ref in case["source_refs"]):
            raise ValueError(f"Unknown source: {case['id']}")
    if read_jsonl(directory / "retrieval_th.jsonl") != [c for c in cases if c["expected"]]:
        raise ValueError("Retrieval export differs from master dataset")
    return cases


def score(cases: list[dict], predictions: list[dict], dataset_version: str = "1.0.0") -> dict:
    """Missing outputs fail; unavailable human judgements remain explicitly ungraded."""
    known = {c["id"] for c in cases}
    indexed = {}
    for prediction in predictions:
        key = prediction["id"]
        if key not in known or key in indexed:
            raise ValueError(f"Unknown or duplicate prediction id: {key}")
        ranked = prediction.get("retrieved_chunk_ids", [])
        if not isinstance(ranked, list) or any(not isinstance(x, str) for x in ranked):
            raise ValueError(f"Invalid ranked chunk list: {key}")
        if len(ranked) != len(set(ranked)):
            raise ValueError(f"Duplicate ranked chunks: {key}")
        if "route" in prediction and not isinstance(prediction["route"], str):
            raise ValueError(f"Invalid route: {key}")
        if "answer" in prediction and not isinstance(prediction["answer"], str):
            raise ValueError(f"Invalid answer: {key}")
        indexed[key] = prediction
    retrieval = [c for c in cases if c["expected"]]
    routing = [c for c in cases if c["expected_route"]]
    hits = Counter()
    reciprocal = 0.0
    categories: dict[str, Counter] = {}
    for case in retrieval:
        ranked = indexed.get(case["id"], {}).get("retrieved_chunk_ids", [])[:3]
        relevant = set(case["expected"])
        hit1 = bool(relevant.intersection(ranked[:1]))
        hit3 = bool(relevant.intersection(ranked))
        hits[1] += hit1
        hits[3] += hit3
        reciprocal += next((1 / i for i, x in enumerate(ranked, 1) if x in relevant), 0)
        group = categories.setdefault(case["category"], Counter())
        group["count"] += 1
        group["hit_at_3"] += hit3
    correct = sum(
        indexed.get(c["id"], {}).get("route") == c["expected_route"] for c in routing
    )
    confusion = Counter(
        (c["expected_route"], indexed.get(c["id"], {}).get("route", "MISSING"))
        for c in routing
    )
    graded = passed = 0
    criteria_total = sum(len(c["criteria"]) for c in cases)
    for case in cases:
        prediction = indexed.get(case["id"], {})
        labels = prediction.get("criteria_pass", {})
        allowed = {item["id"] for item in case["criteria"]}
        if not isinstance(labels, dict) or not set(labels) <= allowed:
            raise ValueError(f"Unknown rubric criterion: {case['id']}")
        if labels and (
            not prediction.get("answer", "").strip()
            or not prediction.get("reviewer", "").strip()
        ):
            raise ValueError(
                f"Human rubric labels require answer and reviewer: {case['id']}"
            )
        for label in labels.values():
            if type(label) is not bool:
                raise ValueError("Rubric labels must be true/false")
            graded += 1
            passed += label
    return {
        "dataset_version": dataset_version,
        "prediction_count": len(indexed),
        "retrieval": {
            "case_count": len(retrieval),
            "output_coverage": sum(
                "retrieved_chunk_ids" in indexed.get(c["id"], {}) for c in retrieval
            )
            / len(retrieval),
            "hit_at_1": hits[1] / len(retrieval),
            "hit_at_3": hits[3] / len(retrieval),
            "mrr_at_3": reciprocal / len(retrieval),
            "by_category": {
                k: {"count": v["count"], "hit_at_3": v["hit_at_3"] / v["count"]}
                for k, v in categories.items()
            },
        },
        "routing": {
            "status": (
                "evaluated"
                if any("route" in indexed.get(c["id"], {}) for c in routing)
                else "not_evaluated"
            ),
            "case_count": len(routing),
            "output_coverage": sum("route" in indexed.get(c["id"], {}) for c in routing)
            / len(routing),
            "accuracy": correct / len(routing),
            "confusion": [
                {"expected": a, "predicted": b, "count": n}
                for (a, b), n in sorted(confusion.items())
            ],
        },
        "answer_review": {
            "criteria_total": criteria_total,
            "criteria_graded": graded,
            "coverage": graded / criteria_total,
            "pass_rate_on_graded": passed / graded if graded else None,
            "passed_fraction_of_all_criteria": passed / criteria_total,
        },
    }


def retrieve(cases: list[dict], mode: str, model: str) -> list[dict]:
    # No API keys, accounts, or personal data are accessed here.
    from app.rag.chunking import load_chunks
    from app.rag.hybrid import search
    from app.rag.snapshot import IndexedChunk, SearchFilters, Snapshot
    from app.rag.tokenize import tokenize

    if mode == "bm25":
        import numpy as np

        # Vectors are unused by production BM25 search; no model is downloaded.
        records = [
            IndexedChunk(c, np.zeros(1, dtype=np.float32), tuple(tokenize(c.text)))
            for c in load_chunks(str(REPO / "data"))
        ]
        snapshot = Snapshot(records, dimension=1)
        return [
            {
                "id": c["id"],
                "retrieved_chunk_ids": [
                    h.chunk.chunk_id
                    for h in search(
                        snapshot,
                        None,
                        query=c["query"],
                        top_k=3,
                        filters=SearchFilters(),
                        mode="bm25",
                    )
                ],
            }
            for c in cases
            if c["expected"]
        ]

    from app.rag.embedder import SentenceTransformerEmbedder
    from app.rag.index import RagIndex

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        index = RagIndex(
            data_dir=str(REPO / "data"),
            db_path=f"{folder}/rag.db",
            embedder=SentenceTransformerEmbedder(model),
        )
        index.build()
        return [
            {
                "id": c["id"],
                "retrieved_chunk_ids": [
                    h.chunk.chunk_id
                    for h in index.search(c["query"], top_k=3, mode=mode)
                ],
            }
            for c in cases
            if c["expected"]
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("v1", "v2"), default="v1")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--predictions", type=Path)
    action.add_argument("--retrieve", choices=("bm25", "vector", "hybrid"))
    parser.add_argument("--model", default="intfloat/multilingual-e5-base")
    parser.add_argument(
        "--output", type=Path, help="Save report JSON (prints when omitted)"
    )
    parser.add_argument("--save-predictions", type=Path)
    args = parser.parse_args()
    directory = HERE.with_name(f"careermirror_{args.suite}")
    cases = validate(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if args.predictions or args.retrieve:
        predictions = (
            read_jsonl(args.predictions)
            if args.predictions
            else retrieve(cases, args.retrieve, args.model)
        )
        report = score(cases, predictions, manifest["dataset_version"])
        report["run"] = {
            "retrieval_mode": args.retrieve,
            "embedding_model": args.model
            if args.retrieve in ("vector", "hybrid")
            else None,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "python": sys.version.split()[0],
            "dataset_sha256": fingerprint(directory / "golden_th.jsonl"),
        }
        if args.retrieve:
            report["run"]["packages"] = {
                name: version(name)
                for name in ("numpy", "rank-bm25", "pythainlp", "faiss-cpu")
            }
        if args.save_predictions:
            args.save_predictions.write_text(
                "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in predictions),
                encoding="utf-8",
            )
    else:
        report = {
            "valid": True,
            "cases": len(cases),
            "status": "draft_pending_human_review",
        }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
