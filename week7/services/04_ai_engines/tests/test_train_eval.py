"""
[รีวิว PR #21 รอบ 2] กัน regression ของเส้นทางเทรน/ประเมินใน train.py
`pytest -q tests` เดิมไม่ได้รัน train.py เลย จึงไม่จับ KeyError ของรูปแบบ fixture (`intent` vs `expected_intent`)
และเคส `clarify` ที่ไม่มี label ใน classifier

หมายเหตุ: ต้องมี pandas/scikit-learn/joblib ใน dependency ที่ CI ติดตั้ง (ดู requirements*.txt)
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import train  # noqa: E402

INTENTS = [f"intent_{i}" for i in range(8)]


def _write_dataset(path: Path) -> None:
    rows = ["text,intent"]
    for i, intent in enumerate(INTENTS):
        for j in range(6):
            rows.append(f"คำถามหมวด{i} ตัวอย่างที่{j} keyword{i}{i}{i},{intent}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_cases(path: Path, key: str) -> None:
    cases = [
        {"query": "คำถามหมวด0 ตัวอย่างที่9 keyword000", key: "intent_0"},
        {"query": "คำถามหมวด3 ตัวอย่างที่9 keyword333", key: "intent_3"},
        {"query": "ช่วยอธิบายหน่อย", key: "clarify"},  # ไม่มี label ใน classifier ต้องถูกข้าม
    ]
    path.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")


def _fit_pipeline(tmp_path: Path):
    data = tmp_path / "intents.csv"
    _write_dataset(data)
    df = train._load_dataset(data)
    pipe = train._fresh_pipeline()
    pipe.fit(df["text"].tolist(), df["intent"].tolist())
    return pipe


@pytest.mark.parametrize("key", ["intent", "expected_intent"])
def test_evaluate_supports_both_fixture_key_formats_and_skips_clarify(tmp_path, capsys, key):
    pipe = _fit_pipeline(tmp_path)
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, key)

    train.evaluate_on_routing_cases(pipe, cases_path, "fixture")  # ต้องไม่โยน KeyError

    out = capsys.readouterr().out
    assert "(2 เคส)" in out
    assert "ข้าม 1 เคส" in out
    assert "accuracy:" in out


def test_evaluate_skips_when_no_case_matches_model_classes(tmp_path, capsys):
    pipe = _fit_pipeline(tmp_path)
    cases_path = tmp_path / "only_clarify.jsonl"
    cases_path.write_text(json.dumps({"query": "x", "intent": "clarify"}) + "\n", encoding="utf-8")

    train.evaluate_on_routing_cases(pipe, cases_path, "fixture")

    assert "ไม่มีเคสที่ label อยู่ในคลาสของโมเดลเลย" in capsys.readouterr().out


def test_main_end_to_end_with_real_intent_fixture(tmp_path, monkeypatch, capsys):
    """รัน train.main() จริงทั้งเส้นทาง (เทรน → เซฟโมเดล → ประเมินกับ fixture รูปแบบ `intent` + clarify)"""
    data = tmp_path / "intents.csv"
    _write_dataset(data)
    cases_path = tmp_path / "routing_cases.jsonl"
    _write_cases(cases_path, "intent")
    model_dir = tmp_path / "models"

    monkeypatch.setattr(train, "DATA_PATH", data)
    monkeypatch.setattr(train, "MODEL_DIR", model_dir)
    monkeypatch.setattr(train, "MODEL_PATH", model_dir / "intent_clf.joblib")
    monkeypatch.setattr(train, "REAL_ROUTING_CASES", cases_path)

    train.main()

    assert (model_dir / "intent_clf.joblib").exists()
    out = capsys.readouterr().out
    assert "ข้าม 1 เคส" in out


# ---------------------------------------------------------------------------
# [รีวิว PR #21 รอบ 3] กัน data leakage: ข้อมูลฝึกต้องไม่ซ้ำกับชุด routing cases
# ---------------------------------------------------------------------------
import pandas as pd  # noqa: E402


def test_find_overlap_normalizes_whitespace_and_case():
    cases = [{"query": "Who  won   the League"}, {"query": "ช่วยอธิบายหน่อย", "intent": "clarify"}]
    assert train.find_overlap(["who won the league ", "อย่างอื่น"], cases) == {"who won the league"}
    assert train.find_overlap(["ช่วยอธิบายหน่อย"], cases)  # clarify ก็นับว่าซ้ำ


def test_drop_overlap_removes_rows_and_reports_count():
    df = pd.DataFrame({"text": ["a b", "c", "A  B"], "intent": ["x", "y", "x"]})
    out, dropped = train.drop_overlap(df, [{"query": "a b"}])
    assert dropped == 2 and out["text"].tolist() == ["c"]


def test_main_drops_overlapping_rows_before_training(tmp_path, monkeypatch, capsys):
    data = tmp_path / "intents.csv"
    _write_dataset(data)
    # เติมแถวที่ซ้ำกับเคสของ router ตรง ๆ
    with open(data, "a", encoding="utf-8") as f:
        f.write("คำถามหมวด0 ตัวอย่างที่9 keyword000,intent_0\n")
    cases_path = tmp_path / "routing_cases.jsonl"
    _write_cases(cases_path, "intent")
    model_dir = tmp_path / "models"
    monkeypatch.setattr(train, "DATA_PATH", data)
    monkeypatch.setattr(train, "MODEL_DIR", model_dir)
    monkeypatch.setattr(train, "MODEL_PATH", model_dir / "intent_clf.joblib")
    monkeypatch.setattr(train, "REAL_ROUTING_CASES", cases_path)

    train.main()

    out = capsys.readouterr().out
    assert "ตัดแถวฝึกที่ซ้ำ" in out and "1 แถว" in out
    import joblib
    assert joblib.load(model_dir / "intent_clf.joblib")["trained_on_rows"] == 48


@pytest.mark.parametrize("attr", ["REAL_ROUTING_CASES", "SIMULATED_ROUTING_CASES"])
def test_repo_intents_do_not_overlap_routing_cases(attr):
    """regression ของจริง: data/intents.csv ต้องไม่มีประโยคซ้ำกับ routing cases (ข้ามถ้าไม่มีไฟล์)"""
    path = getattr(train, attr)
    if not path.exists():
        pytest.skip(f"ไม่พบ {path}")
    df = train._load_dataset(train.DATA_PATH)
    overlap = train.find_overlap(df["text"].tolist(), train._load_jsonl_cases(path))
    assert not overlap, f"ข้อมูลฝึกซ้ำกับ {path.name}: {sorted(overlap)}"