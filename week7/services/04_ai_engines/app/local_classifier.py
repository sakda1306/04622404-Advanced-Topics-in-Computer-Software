"""
โหลดโมเดล TF-IDF + LogisticRegression ที่เทรนไว้แล้ว (train.py) มาใช้ตอบ POST /local/classify
โหลดครั้งเดียวตอน process เริ่ม (module-level singleton) ไม่โหลดใหม่ทุก request
"""
import logging
from pathlib import Path
from typing import Optional

import joblib

logger = logging.getLogger("engines")

MODEL_PATH = Path(__file__).resolve().parent / "models" / "intent_clf.joblib"

_bundle: Optional[dict] = None


class ModelNotLoadedError(Exception):
    """โมเดลยังไม่ถูกเทรน/ไฟล์หาย — main.py แปลงเป็น 503 MODEL_UNAVAILABLE"""


def load_model() -> dict:
    global _bundle
    if _bundle is None:
        if not MODEL_PATH.exists():
            raise ModelNotLoadedError(
                f"ไม่พบโมเดลที่ {MODEL_PATH} — รัน `python train.py` ก่อน"
            )
        _bundle = joblib.load(MODEL_PATH)
        logger.info(
            '{"event":"model_loaded","model_version":"%s","trained_on_rows":%d}',
            _bundle["model_version"],
            _bundle["trained_on_rows"],
        )
    return _bundle


def classify(text: str, top_k: int = 3) -> dict:
    """
    คืน dict ตรงกับ field `data` ของ EngineResult:
    { "label": "match_result", "score": 0.88, "top_k": [["match_result", 0.88], ...] }
    """
    bundle = load_model()
    pipeline = bundle["pipeline"]

    proba = pipeline.predict_proba([text])[0]
    classes = pipeline.classes_
    ranked = sorted(zip(classes, proba), key=lambda x: x[1], reverse=True)

    label, score = ranked[0]
    return {
        "label": str(label),
        "score": round(float(score), 4),
        "top_k": [[str(c), round(float(s), 4)] for c, s in ranked[:top_k]],
    }


def model_version() -> str:
    return load_model()["model_version"]
