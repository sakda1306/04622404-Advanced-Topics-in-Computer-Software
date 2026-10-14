"""
D3 — เทรน intent classifier: TF-IDF + LogisticRegression
รัน: python train.py

ทำ:
1. โหลด data/intents.csv (8 หมวด)
2. แบ่ง train/test แบบ stratified (80/20) เพื่อวัด accuracy บนข้อมูลของเราเอง
3. เทรนบน "ข้อมูลทั้งหมด" (ไม่ใช่แค่ train split) แล้วเซฟโมเดลไปใช้จริงที่ /local/classify
   — เพราะข้อมูลของเรามีน้อย (240 แถว) การเก็บ test split ไว้เฉย ๆ ไม่ใช้เทรนจะเสียของ
   — accuracy ที่รายงานยังมาจาก held-out split เท่านั้น ไม่ปนกับที่เทรนจริง
4. ถ้าเจอ tests/routing_cases.jsonl ของ member2 (40 เคสจริง) จะรันวัดผลกับชุดนั้นด้วย
   — ชุดนี้ "ห้ามเอามาเทรนเด็ดขาด" ตามที่ SCHEDULE.md กำชับ ใช้วัดผลอย่างเดียว
"""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "intents.csv"
MODEL_DIR = ROOT / "app" / "models"
MODEL_PATH = MODEL_DIR / "intent_clf.joblib"
MODEL_VERSION = "tfidf-logreg-v1"

# path ของ 03 ตาม 00_PLAN_OVERVIEW.md §158 — จะมีจริงเมื่อ member2 commit เข้า repo กลาง
REAL_ROUTING_CASES = ROOT.parent / "03_ai_router_agent" / "tests" / "routing_cases.jsonl"
# ชุดจำลองของเราเอง ใช้แทนชั่วคราวถ้ายังไม่มีไฟล์จริง (D4 ใช้ไฟล์นี้เดโมกระบวนการ)
SIMULATED_ROUTING_CASES = ROOT / "tests" / "simulated_routing_cases.jsonl"


def _load_dataset(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    assert {"text", "intent"}.issubset(df.columns), f"{path} ต้องมีคอลัมน์ text,intent"
    return df


def _load_jsonl_cases(path: Path) -> list[dict]:
    cases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _case_intent(c: dict) -> str | None:
    # ไฟล์จริงบน develop ใช้ key "intent"; ชุดจำลองของเราใช้ "expected_intent" — รองรับทั้งสอง
    return c.get("expected_intent", c.get("intent"))


def _normalize_text(text: str) -> str:
    """normalize ก่อนเทียบซ้ำ: NFKC + ยุบช่องว่าง + lowercase (กันซ้ำแบบต่างแค่ช่องว่าง/ตัวพิมพ์)"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text))).strip().lower()


def find_overlap(texts: list[str], cases: list[dict]) -> set[str]:
    """คืนชุดข้อความ (normalized) ที่อยู่ทั้งในข้อมูลฝึกและในชุด routing cases (ทุกเคส รวม clarify)"""
    case_queries = {_normalize_text(c["query"]) for c in cases if "query" in c}
    return {_normalize_text(t) for t in texts} & case_queries


def drop_overlap(df: pd.DataFrame, cases: list[dict]) -> tuple[pd.DataFrame, int]:
    """ตัดแถวฝึกที่ซ้ำกับชุด routing cases ออก คืน (df ใหม่, จำนวนที่ตัด) — ชุดนี้ใช้วัดผลอย่างเดียว"""
    overlap = find_overlap(df["text"].tolist(), cases)
    if not overlap:
        return df, 0
    keep = ~df["text"].map(_normalize_text).isin(overlap)
    return df[keep].reset_index(drop=True), int((~keep).sum())


def evaluate_on_routing_cases(pipeline: Pipeline, path: Path, label: str) -> None:
    if not path.exists():
        print(f"[skip] ไม่พบ {label} ที่ {path}")
        return
    all_cases = _load_jsonl_cases(path)

    # classifier ทายได้เฉพาะ 8 คลาสที่เทรน — เคสที่ label อยู่นอกนี้ (เช่น clarify) วัดไม่ได้
    # จึงกรองออก ไม่งั้นจะนับเป็นผิดทุกครั้ง
    labels = set(pipeline.classes_)
    cases = [c for c in all_cases if _case_intent(c) in labels]
    skipped = len(all_cases) - len(cases)
    if not cases:
        print(f"[skip] {label}: ไม่มีเคสที่ label อยู่ในคลาสของโมเดลเลย (จากทั้งหมด {len(all_cases)} เคส)")
        return

    texts = [c["query"] for c in cases]
    y_true = [_case_intent(c) for c in cases]
    y_pred = pipeline.predict(texts)
    acc = accuracy_score(y_true, y_pred)
    print(f"\n=== ผลบน {label} ({len(cases)} เคส) — ไม่ได้เทรนด้วยชุดนี้ ===")
    if skipped:
        print(f"(ข้าม {skipped} เคสที่ label ไม่อยู่ใน {len(labels)} คลาสของโมเดล เช่น clarify)")
    print(f"accuracy: {acc:.3f}")
    misses = [
        {"query": t, "expected": e, "predicted": p}
        for t, e, p in zip(texts, y_true, y_pred)
        if e != p
    ]
    if misses:
        print(f"พลาด {len(misses)} เคส:")
        for m in misses:
            print(f"  - \"{m['query']}\" → ทาย {m['predicted']} (ที่ถูก: {m['expected']})")
    else:
        print("ไม่พลาดเลย 🎉")


def main():
    df = _load_dataset(DATA_PATH)

    # กัน data leakage: ชุด routing cases ใช้วัดผลอย่างเดียว ถ้าประโยคไหนซ้ำกับข้อมูลฝึก
    # ตัดออกจากข้อมูลฝึก "ก่อนแบ่ง split/เทรน/วัดผล" ทั้งสองรอบ แล้วเตือนให้ไปแก้ที่ data/intents.csv
    routing_path = REAL_ROUTING_CASES if REAL_ROUTING_CASES.exists() else SIMULATED_ROUTING_CASES
    if routing_path.exists():
        df, dropped = drop_overlap(df, _load_jsonl_cases(routing_path))
        if dropped:
            print(f"[คำเตือน] ตัดแถวฝึกที่ซ้ำกับ {routing_path.name} ออก {dropped} แถว — ควรแก้ที่ data/intents.csv")
    X, y = df["text"].tolist(), df["intent"].tolist()

    # 1) วัด accuracy แบบ held-out (ไม่ปนกับโมเดลที่จะเอาไปใช้จริง)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    eval_pipeline = _fresh_pipeline()
    eval_pipeline.fit(X_train, y_train)
    y_pred = eval_pipeline.predict(X_test)
    held_out_acc = accuracy_score(y_test, y_pred)

    print(f"โหลดข้อมูล: {len(df)} แถว, {df['intent'].nunique()} หมวด")
    print(f"\n=== held-out accuracy (20% ของ data/intents.csv) ===")
    print(f"accuracy: {held_out_acc:.3f}")
    print(classification_report(y_test, y_pred, zero_division=0))

    # 2) เทรนโมเดลจริงด้วยข้อมูลทั้งหมด แล้วเซฟไว้ใช้ที่ /local/classify
    final_pipeline = _fresh_pipeline()
    t0 = time.monotonic()
    final_pipeline.fit(X, y)
    train_ms = int((time.monotonic() - t0) * 1000)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": final_pipeline,
            "model_version": MODEL_VERSION,
            "classes": sorted(set(y)),
            "trained_on_rows": len(df),
            "held_out_accuracy": round(held_out_acc, 4),
        },
        MODEL_PATH,
    )
    print(f"\nเทรนจบใน {train_ms}ms → เซฟโมเดลที่ {MODEL_PATH}")

    # 3) วัดกับ routing cases จริง (ถ้ามี) ไม่งั้นใช้ชุดจำลองแทน — ใช้โมเดลที่เทรนด้วย held-out split
    #    (ไม่ใช่โมเดล final ที่เทรนด้วยข้อมูลทั้งหมด กันไม่ให้ตัวเลข "รั่ว" กรณีบางเคสซ้ำกับ dataset)
    if REAL_ROUTING_CASES.exists():
        evaluate_on_routing_cases(eval_pipeline, REAL_ROUTING_CASES, "tests/routing_cases.jsonl (ของจริงจาก member2)")
    else:
        evaluate_on_routing_cases(
            eval_pipeline,
            SIMULATED_ROUTING_CASES,
            "tests/simulated_routing_cases.jsonl (ชุดจำลอง — ยังไม่ได้ไฟล์จริงจาก member2)",
        )


def _fresh_pipeline() -> Pipeline:
    # analyzer="char_wb" (char n-gram ในขอบเขตคำ) แทน word-level ธรรมดา เพราะ:
    #  - ภาษาไทยไม่มีช่องว่างคั่นคำ ถ้าตัดด้วย whitespace ประโยคไทยจะกลายเป็น "คำ" เดียวยาว ๆ
    #    (เช่น "ลิเวอร์พูลกับซิตี้ใครน่าจะชนะ" ไม่มีช่องว่างเลย) ทำให้ TF-IDF แทบไร้ประโยชน์
    #  - ไม่ต้องพึ่ง Thai word segmenter (เช่น pythainlp) เพิ่ม dependency
    #  - char n-gram (2-4 ตัวอักษร) จับ substring ของชื่อทีม/คำสำคัญได้ทั้งไทยและอังกฤษในตัวเดียว
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(2, 4),
                    min_df=1,
                    sublinear_tf=True,
                ),
            ),
            ("clf", LogisticRegression(max_iter=2000, C=5.0)),
        ]
    )


if __name__ == "__main__":
    sys.exit(main())