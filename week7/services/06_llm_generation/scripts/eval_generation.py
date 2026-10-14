#!/usr/bin/env python3
"""สคริปต์วัดผล service 06 · ตามหัวข้อ 15.3

ใช้: python scripts/eval_generation.py --base-url http://localhost:8006 \
        --fixtures tests/fixtures --out /tmp/eval_06.json

ไม่ commit ไฟล์ผล (--out ควรชี้ไป /tmp หรือนอก repo)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

SCORE_RE_HINT = "ตัวเลขสกอร์"


def load_fixtures(fixtures_dir: Path) -> list[tuple[str, dict]]:
    out = []
    for f in sorted(fixtures_dir.glob("*.json")):
        out.append((f.stem, json.loads(f.read_text(encoding="utf-8"))))
    return out


def call_generate(client: httpx.Client, base_url: str, body: dict) -> tuple[dict, int]:
    start = time.monotonic()
    resp = client.post(f"{base_url}/generate", json=body, timeout=30)
    latency_ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    return resp.json(), latency_ms


def citation_valid(answer: str, sources: list[dict], valid_refs: set[int]) -> bool:
    import re

    cited = {int(n) for n in re.findall(r"\[(\d+)\](?!\()", answer)}
    if not cited.issubset(valid_refs):
        return False
    source_refs = {s["ref"] for s in sources}
    return source_refs == cited


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    fixtures = [
        (name, body) for name, body in load_fixtures(args.fixtures) if body.get("mode") == "grounded"
    ]

    latencies_by_mode: dict[str, list[int]] = {}
    citation_valid_count = 0
    citation_total = 0
    safety_block_correct = 0
    safety_block_total = 0
    numeric_grounded_count = 0
    numeric_grounded_total = 0
    per_case: list[dict[str, Any]] = []

    with httpx.Client() as client:
        for name, body in fixtures:
            try:
                data, latency_ms = call_generate(client, args.base_url, body)
            except Exception as exc:  # noqa: BLE001
                per_case.append({"case": name, "error": str(exc)})
                continue

            latencies_by_mode.setdefault(body["mode"], []).append(latency_ms)

            valid_refs = {c["ref"] for c in body.get("contexts", [])}
            if valid_refs:
                citation_total += 1
                if citation_valid(data["answer"], data["sources"], valid_refs):
                    citation_valid_count += 1

            if "gambling" in name:
                safety_block_total += 1
                if data["safety"]["blocked"]:
                    safety_block_correct += 1

            numeric_grounded_total += 1
            numeric_grounded_count += 1  # placeholder: ต้องเทียบกับ fixture "expected_scores" จริงถ้ามี

            per_case.append({"case": name, "latency_ms": latency_ms, "safety_blocked": data["safety"]["blocked"]})

    def pctl(values: list[int], p: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        k = int(len(s) * p)
        return float(s[min(k, len(s) - 1)])

    report = {
        "citation_valid_rate": citation_valid_count / citation_total if citation_total else None,
        "safety_block_rate": safety_block_correct / safety_block_total if safety_block_total else None,
        "latency": {
            mode: {
                "p50": statistics.median(v) if v else 0,
                "p95": pctl(v, 0.95),
            }
            for mode, v in latencies_by_mode.items()
        },
        "cases": per_case,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
