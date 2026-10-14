#!/usr/bin/env python3
"""ตรวจว่าตัวเลขใน markdown ของ /report/weekly ตรงกับข้อมูลต้นทาง (request)

ใช้: python scripts/check_report_numbers.py --request req.json --response resp.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.numeric_guard import check_score_mismatch


def known_scores_from_request(req: dict) -> set[tuple[int, int]]:
    scores = set()
    for m in req.get("matches", []):
        score = m.get("score")
        if m.get("status") == "FINISHED" and score and score.get("home") is not None:
            scores.add((score["home"], score["away"]))
    return scores


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True, type=Path)
    ap.add_argument("--response", required=True, type=Path)
    args = ap.parse_args()

    req = json.loads(args.request.read_text(encoding="utf-8"))
    resp = json.loads(args.response.read_text(encoding="utf-8"))

    known = known_scores_from_request(req)
    mismatches = check_score_mismatch(resp["markdown"], known)

    if mismatches:
        print(f"FAIL: พบสกอร์ที่ไม่ตรงกับข้อมูลต้นทาง: {mismatches}", file=sys.stderr)
        return 1

    highlight_text = " ".join(resp.get("highlights", []))
    highlight_mismatches = check_score_mismatch(highlight_text, known)
    if highlight_mismatches:
        print(f"FAIL: พบสกอร์ที่ไม่ตรงกับข้อมูลต้นทางใน highlights: {highlight_mismatches}", file=sys.stderr)
        return 1

    print("OK: ตัวเลขสกอร์ในรายงานตรงกับข้อมูลต้นทางทั้งหมด")
    return 0


if __name__ == "__main__":
    sys.exit(main())
