"""Refresh expiry times in synthetic examples before a demo."""

import json
from pathlib import Path

from decision_engine.sample_data import scenarios

out = Path(__file__).resolve().parents[1] / "examples"
out.mkdir(exist_ok=True)
for name, payload in scenarios().items():
    (out / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
print(f"Refreshed {len(scenarios())} synthetic examples in {out}")
