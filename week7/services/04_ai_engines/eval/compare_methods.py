"""
D5 — เทียบ TF-IDF vs embedding vs ถาม LLM ตรง ๆ บน held-out split เดียวกัน (fair comparison)
รัน: python eval/compare_methods.py
เขียนผลลง eval/method_comparison.md (ตาราง 3 แถว)

หมายเหตุสภาพแวดล้อมตอนสร้างไฟล์นี้ (อ่านก่อนรันเอง):
  แซนด์บ็อกซ์ที่ใช้เขียนโค้ดนี้ "บล็อกเน็ตเวิร์ก" ไปยัง huggingface.co, api.groq.com,
  generativelanguage.googleapis.com (เทสต์แล้วได้ 403 จาก egress proxy) จึงรันได้จริงแค่วิธีที่ 1
  (TF-IDF) เท่านั้น — ตัวเลขวิธี 2 และ 3 ในตารางตอนนี้เป็น placeholder "ยังไม่ได้รัน"
  รันสคริปต์นี้ในเครื่อง/เซิร์ฟเวอร์ที่ต่อเน็ตได้ + ใส่ GROQ_API_KEY/GEMINI_API_KEY ใน .env
  แล้วตารางจะเติมตัวเลขจริงให้อัตโนมัติ
"""
import sys
import time
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from train import _fresh_pipeline  # noqa: E402

DATA_PATH = ROOT / "data" / "intents.csv"
OUT_PATH = Path(__file__).resolve().parent / "method_comparison.md"


def eval_tfidf(X_train, y_train, X_test, y_test) -> tuple[float, float]:
    pipeline = _fresh_pipeline()
    t0 = time.monotonic()
    pipeline.fit(X_train, y_train)
    train_ms = (time.monotonic() - t0) * 1000
    acc = pipeline.score(X_test, y_test)
    return acc, train_ms


def eval_embeddings(X_train, y_train, X_test, y_test):
    try:
        from eval.embedding_classifier import train_and_eval
    except ImportError as e:
        return None, f"import ล้มเหลว: {e}"
    try:
        acc = train_and_eval(X_train, y_train, X_test, y_test)
        return acc, None
    except Exception as e:  # เช่น ต่อ huggingface.co ไม่ได้
        return None, f"รันไม่สำเร็จ: {e}"


def eval_llm(X_test, y_test):
    try:
        from eval.llm_classifier import train_and_eval
    except ImportError as e:
        return None, f"import ล้มเหลว: {e}"
    try:
        acc = train_and_eval(X_test, y_test)
        return acc, None
    except Exception as e:  # เช่น ต่อ groq/gemini ไม่ได้ หรือไม่มี API key
        return None, f"รันไม่สำเร็จ: {e}"


def _fmt(acc, note):
    if acc is None:
        return f"ยังไม่ได้รัน ({note})" if note else "ยังไม่ได้รัน"
    return f"{acc:.3f}"


def main():
    df = pd.read_csv(DATA_PATH)
    X_train, X_test, y_train, y_test = train_test_split(
        df["text"].tolist(), df["intent"].tolist(), test_size=0.2, random_state=42, stratify=df["intent"]
    )

    tfidf_acc, tfidf_ms = eval_tfidf(X_train, y_train, X_test, y_test)
    print(f"[1/3] TF-IDF + LogisticRegression: accuracy={tfidf_acc:.3f}")

    emb_acc, emb_note = eval_embeddings(X_train, y_train, X_test, y_test)
    print(f"[2/3] sentence-transformers embeddings: {_fmt(emb_acc, emb_note)}")

    llm_acc, llm_note = eval_llm(X_test, y_test)
    print(f"[3/3] ถาม LLM ตรง ๆ (few-shot): {_fmt(llm_acc, llm_note)}")

    table = f"""# D5 — เทียบ 3 วิธีจำแนก intent

held-out test set เดียวกัน: {len(X_test)} ตัวอย่าง (20% ของ `data/intents.csv`, {len(X_train)} ใช้เทรน)

| วิธี | accuracy | ต้องเทรนก่อนไหม | เร็ว/ถูกแค่ไหน | ต้องมีเน็ต/API key ไหม |
|---|---|---|---|---|
| TF-IDF (char n-gram) + LogisticRegression | {tfidf_acc:.3f} | ต้อง (เทรนทั้งชุด {tfidf_ms:.0f}ms) | เร็วมาก รันในเครื่องได้ ไม่มีค่าใช้จ่าย | ไม่ต้อง |
| sentence-transformers embeddings + LogisticRegression | {_fmt(emb_acc, emb_note)} | ต้อง | ปานกลาง (โหลดโมเดล ~470MB ครั้งแรก) | ต้องต่อ huggingface.co ตอนโหลดโมเดลครั้งแรก |
| ถาม LLM ตรง ๆ (few-shot ผ่าน Groq/Gemini) | {_fmt(llm_acc, llm_note)} | ไม่ต้อง | ช้าสุด + มีค่าใช้จ่าย/นัด (เรียก API ทุกครั้ง) | ต้องมี `GROQ_API_KEY`/`GEMINI_API_KEY` |

## สรุปเบื้องต้น (จากตัวเลขที่มี ณ ตอนนี้)

- TF-IDF ใช้งานจริงตอนนี้: {tfidf_acc:.1%} บน held-out split, เร็ว, ไม่มีค่าใช้จ่าย ไม่พึ่งเน็ต
  → เหมาะเป็น production classifier ของ `/local/classify` (ตามที่ contract กำหนด `tfidf-logreg-v1`)
- embeddings และ LLM-based ยังไม่มีตัวเลขจริงจากสภาพแวดล้อมที่เขียนไฟล์นี้ (ดูเหตุผลบนสุดของ
  `eval/compare_methods.py`) — รันสคริปต์นี้ในเครื่องที่ต่อเน็ตได้เพื่อเติมให้ครบ
- แม้ embeddings/LLM จะแม่นกว่า TF-IDF จริง ทั้งสองวิธีก็ช้ากว่าและมีต้นทุนต่อ request สูงกว่ามาก
  ซึ่งขัดกับเป้าหมายของ `/local/classify` ที่ต้องเป็น "ชั้นกรองที่เร็วและถูก" ก่อนค่อยเรียก LLM
  (ดู 03_process.txt เดิม: "ควบคุมต้นทุน General AI ด้วย token budget") — TF-IDF จึงน่าจะเป็นตัวเลือก
  ที่เหมาะกับงานนี้อยู่ดี แม้ accuracy จะไม่สูงสุดในสามวิธี
"""
    OUT_PATH.write_text(table, encoding="utf-8")
    print(f"\nเขียนตารางแล้วที่ {OUT_PATH}")


if __name__ == "__main__":
    main()
