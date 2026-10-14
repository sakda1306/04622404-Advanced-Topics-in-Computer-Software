"""
D5 — วิธีที่ 2: sentence-transformers embeddings + LogisticRegression

ใช้โมเดล multilingual เพราะ dataset มีทั้งไทย+อังกฤษปนกัน
ต้องโหลดน้ำหนักโมเดลจาก huggingface.co ตอนรันครั้งแรก (แล้ว cache ไว้ในเครื่อง)
"""
from sklearn.linear_model import LogisticRegression


EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def embed_texts(texts: list[str]):
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return model.encode(texts, show_progress_bar=False)


def train_and_eval(X_train, y_train, X_test, y_test) -> float:
    """คืนค่า accuracy บน (X_test, y_test) — raise ถ้าโหลดโมเดลไม่ได้ (เช่นไม่มีเน็ต)"""
    train_emb = embed_texts(X_train)
    test_emb = embed_texts(X_test)

    clf = LogisticRegression(max_iter=2000)
    clf.fit(train_emb, y_train)
    return clf.score(test_emb, y_test)
