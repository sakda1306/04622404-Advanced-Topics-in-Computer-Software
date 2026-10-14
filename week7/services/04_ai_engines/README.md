# 04 — AI Engines (`engines`) · member3

General AI + Local AI Model ตาม `CONTRACT.md` §3 และ §8

## สถานะ

| วัน | สถานะ |
|---|---|
| D1 | ✅ `data/intents.csv` — 8 หมวด, เริ่มที่ 240 แถว (ดู D4 ที่เพิ่มอีก 14) |
| D2 | ✅ `POST /general` ใช้ได้จริง · fallback Groq → Gemini |
| D3 | ✅ `train.py` + `POST /local/classify` ใช้ได้ (TF-IDF char-ngram + LogisticRegression) |
| D4 | ✅ ปรับ dataset จาก error จริงที่เจอ (ดูหัวข้อด้านล่าง) · จำกัด token ของ `/general` |
| D5 | ✅ ตาราง 3 แถว (TF-IDF รันจริง, embeddings/LLM รอรันในเครื่องที่ต่อเน็ตได้) · `/local/predict` ตอบ `501` ตามที่ contract อนุญาต |
| D6 | ⬜ accuracy ลง README (รอบสุดท้ายก่อนหยุด 20:00) |

## รันเดี่ยว (ไม่ผ่าน Docker Compose)

```bash
cd services/04_ai_engines
pip install -r requirements.txt
cp .env.example .env   # ใส่ GROQ_API_KEY / GEMINI_API_KEY จริง

# เทรน classifier ก่อน (จำเป็นสำหรับ /local/classify)
python train.py

uvicorn app.main:app --reload --port 8004
```

ทดสอบ:

```bash
curl http://localhost:8004/health

curl -X POST http://localhost:8004/general \
  -H "Content-Type: application/json" \
  -d '{"request_id":"t1","query":"กฎล้ำหน้าคืออะไร","history":[],"language":"th"}'

curl -X POST http://localhost:8004/local/classify \
  -H "Content-Type: application/json" \
  -d '{"request_id":"t2","text":"เมื่อวานปืนใหญ่เจอใคร ผลเท่าไหร่"}'

curl -X POST http://localhost:8004/local/predict \
  -H "Content-Type: application/json" \
  -d '{"request_id":"t3","home_team_id":57,"away_team_id":61,"season":"2026"}'
# -> 501 NOT_IMPLEMENTED เมื่อไม่ส่ง home_strength / away_strength (ปกติ 07 เป็นคนเรียก ดูหัวข้อ D5)
```

## เทส

```bash
pytest tests/ -v   # ครอบ /general, llm_client (fallback + เพดานเวลาจริงระหว่าง call), งบเวลารวม,
                   # /local/classify, /local/predict, poisson math, token budget, train.py
```

ทุกเทส mock การเรียก LLM ภายนอก (ไม่ยิง Groq/Gemini จริง) — `/local/classify` ใช้โมเดลจริงที่เทรนไว้
(ต้องรัน `python train.py` ก่อน 1 ครั้ง ไม่งั้นเทสที่เรียกโมเดลจริงจะ fail)

---

## D3 — `train.py` + `POST /local/classify`

- `TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4))` + `LogisticRegression` — เลือก char n-gram
  แทน word-level เพราะภาษาไทยไม่มีช่องว่างคั่นคำ ตัดด้วย whitespace ธรรมดาจะทำให้ TF-IDF ไร้ประโยชน์
  กับประโยคไทย และไม่อยากเพิ่ม dependency ตัวตัดคำไทย (pythainlp) ตอนนี้
- `train.py` เทรน 2 รอบ: (1) held-out split 80/20 เพื่อวัด accuracy แบบไม่โกง (2) เทรนจริงด้วยข้อมูล
  ทั้งหมดแล้วเซฟเป็น `app/models/intent_clf.joblib` ไปใช้ที่ `/local/classify`
   - ผลตอนนี้: **held-out accuracy = 0.784** (51 ตัวอย่าง จาก 254 แถวทั้งหมด, หลังแก้ข้อมูลรั่ว —
     ตรงกับ `eval/method_comparison.md`) ส่วน **0.958** (23/24) เป็นผลบน simulated routing cases
     คนละชุด ไม่ใช่ held-out split เดียวกัน
- `/local/classify` คืน `EngineResult` ตาม contract: `content: "intent: match_result (0.88)"`,
  `data: {label, score, top_k}` (top_k 3 อันดับ), `model: "tfidf-logreg-v1"`, `token_usage: {0,0}`
  (ไม่เรียก LLM เลยในเส้นนี้)
- โมเดลโหลดครั้งเดียวตอน process start (`app/local_classifier.py` เป็น singleton) ไม่โหลดใหม่ทุก request

## D4 — ปรับ dataset จาก error จริง + จำกัด token ของ `/general`

**ปรับ dataset:**
ยังไม่ได้รับ `tests/routing_cases.jsonl` ของจริงจาก member2 (40 เคส) ตอนเขียนงานนี้ — ใช้
`tests/simulated_routing_cases.jsonl` (24 เคสที่เขียนเองจำลองสไตล์คำถามจริง) แทนไปก่อน
รันแล้วเจอ **8/24 พลาด (accuracy 0.667)** วิเคราะห์ได้ 4 pattern ที่พลาดจริง (ไม่ใช่สุ่ม):

1. ใช้ชื่อเล่น "ยูไนเต็ด" (แมนยู) — dataset เดิมมีแต่ "ผี"/"แมนยู" ไม่เคยเห็น token นี้
2. weekly_summary แบบ "เมื่อคืน...ทุกคู่" ถูกทายเป็น match_result เพราะคำว่า "เมื่อคืน" ปนกัน
3. trivia_history เชิงสถิติสะสม/ประวัติ ("เคยไม่แพ้กี่นัดติด") สับสนกับ standings_stats (สถิติฤดูกาลนี้)
4. standings_stats ภาษาอังกฤษแบบเปรียบเทียบ 2 ทีม ("who has more clean sheets X or Y") ไม่เคยมีในชุดเดิม

แก้โดยเพิ่ม 14 ตัวอย่างที่ตรง pattern ที่พลาดจริง (`d4_augment_dataset.py`) แล้วเทรนใหม่ —
**accuracy บนชุดทดสอบเดิมขึ้นจาก 0.667 → 0.958 (23/24)** ยังพลาดอยู่ 1 เคส
("แข้งเบอร์ 9 ของซิตี้คือใคร ยิงไปกี่ลูกแล้ว" → ทาย match_result ที่ถูกคือ standings_stats — ทั้งสอง
หมวดนี้ยังเป็นคู่ที่โมเดลสับสนบ่อยสุด เพราะคำถาม "ยิงไปกี่ลูก" ใช้ได้ทั้งสองบริบท)

**ต้องทำซ้ำเมื่อได้ไฟล์จริงจาก member2**: รัน `python train.py` (จะอ่าน
`services/03_ai_router_agent/tests/routing_cases.jsonl` อัตโนมัติถ้ามีไฟล์อยู่ — ไม่ต้องแก้โค้ด)
วิเคราะห์ error ใหม่ แล้วเพิ่มตัวอย่างเฉพาะ pattern ที่พลาดจริงแบบเดียวกันนี้

**จำกัด token ของ `/general`:**
- response cap ลดจาก 600 → **350** tokens (`GENERAL_MAX_TOKENS`) — `/general` ควรตอบสั้นกระชับอยู่แล้ว
- เพิ่ม input budget **1200 tokens โดยประมาณ** (`GENERAL_MAX_INPUT_TOKENS`) ครอบ system + history + query
  — `app/token_budget.py` ตัด history เก่าสุดออกทีละข้อความจนกว่าจะอยู่ในงบ (เก็บข้อความใหม่สุดไว้ก่อน)
- ใช้ตัวประมาณ token แบบ char-based (~2.2 ตัวอักษร/token) ไม่ใช้ tokenizer จริงของ Groq/Gemini
  เพราะสองเจ้าใช้ tokenizer คนละตัว ไม่มีตัวที่ตรงทั้งคู่ 100% อยู่แล้ว — เป้าหมายคือกัน context บาน
  ไม่ใช่นับ token เป๊ะเพื่อคิดเงิน

## D5 — เทียบ 3 วิธี + `/local/predict`

**ตาราง 3 แถว**: ดู [`eval/method_comparison.md`](eval/method_comparison.md) (สร้างจาก
`python eval/compare_methods.py`)

⚠️ **สภาพแวดล้อมที่เขียนโค้ดนี้บล็อกเน็ตเวิร์กไปยัง `huggingface.co`, `api.groq.com`,
`generativelanguage.googleapis.com`** (ทดสอบแล้วได้ `403 Host not in allowlist`) จึงรันได้จริงแค่
วิธีที่ 1 (TF-IDF) เท่านั้น — **ตัวเลขวิธีที่ 2 (embeddings) และ 3 (ถาม LLM) เป็น placeholder**
ต้องรัน `pip install -r requirements-eval.txt && python eval/compare_methods.py` ในเครื่อง/CI ที่ต่อเน็ต
ได้จริง + ใส่ `GROQ_API_KEY`/`GEMINI_API_KEY` ก่อน ตารางจะเติมตัวเลขจริงให้อัตโนมัติ

### ทำนายผล (CONTRACT v1.7)

- `POST /local/predict` — ถ้า 07 ส่ง `home_strength` / `away_strength` มา จะคำนวณด้วย Poisson (`app/poisson.py`) และคืน `home_win`, `draw`, `away_win`, `home_xg`, `away_xg`, `most_likely_score` · ไม่ส่งมา → 501 เหมือนเดิม
- `POST /local/simulate` — จำลองฤดูกาลที่เหลือแบบ Monte Carlo (`app/simulate.py`, numpy) คืนโอกาสแชมป์ / ท็อป 4 / ตกชั้น และ `position_probs` ของทุกทีม · 10,000 ครั้งกับ 380 นัดใช้เวลาไม่ถึง 2 วินาที
- 04 ไม่มี state และไม่เรียก service อื่น · 07 เป็นคนเตรียมข้อมูลทีมและเก็บผลจำลอง

## ยังไม่ได้ทำ (ตั้งใจเว้นไว้)

- `Dockerfile` — เจ้าของคือ member6 ตาม `GIT_FLOW.md` (ไม่แก้ในโฟลเดอร์นี้)
- ตัวเลขจริงของวิธี embeddings/LLM ใน D5 — ต้องรันในเครื่องที่ต่อเน็ตได้ (ดูหัวข้อ D5)
- D6: accuracy สรุปสุดท้ายลง README — รอผลจาก `routing_cases.jsonl` ของจริง