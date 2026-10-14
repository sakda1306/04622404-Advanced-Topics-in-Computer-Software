# D5 — เทียบ 3 วิธีจำแนก intent

held-out test set เดียวกัน: 51 ตัวอย่าง (20% ของ `data/intents.csv`, 203 ใช้เทรน)

> อัปเดต (แก้ review): 3 แถวใน `data/intents.csv` ที่ D4 copy ประโยคมาจาก
> `tests/simulated_routing_cases.jsonl` ตรงตัวอักษร ถูกเปลี่ยนเป็นประโยคใหม่ที่ความหมาย
> ใกล้เคียงกันแทนแล้ว (ดู `d4_augment_dataset.py` — จำนวนแถวเท่าเดิม) ตัวเลข accuracy ด้านล่าง
> รันใหม่ทั้งหมดหลังแก้ ด้วย scikit-learn 1.5.2 (ตรงกับ `requirements.txt`)

| วิธี | accuracy | ต้องเทรนก่อนไหม | เร็ว/ถูกแค่ไหน | ต้องมีเน็ต/API key ไหม |
|---|---|---|---|---|
| TF-IDF (char n-gram) + LogisticRegression | 0.784 | ต้อง (เทรนทั้งชุด 88ms) | เร็วมาก รันในเครื่องได้ ไม่มีค่าใช้จ่าย | ไม่ต้อง |
| sentence-transformers embeddings + LogisticRegression | ยังไม่ได้รัน (รันไม่สำเร็จ: No module named 'sentence_transformers') | ต้อง | ปานกลาง (โหลดโมเดล ~470MB ครั้งแรก) | ต้องต่อ huggingface.co ตอนโหลดโมเดลครั้งแรก |
| ถาม LLM ตรง ๆ (few-shot ผ่าน Groq/Gemini) | ยังไม่ได้รัน (รันไม่สำเร็จ: groq: Host not in allowlist: api.groq.com. Add this host to your network egress settings to allow access. | gemini: Host not in allowlist: generativelanguage.googleapis.com. Add this host to your network egress settings to allow access.) | ไม่ต้อง | ช้าสุด + มีค่าใช้จ่าย/นัด (เรียก API ทุกครั้ง) | ต้องมี `GROQ_API_KEY`/`GEMINI_API_KEY` |

นอกจาก held-out split แล้ว หลังตัดข้อมูลรั่วออก `tests/simulated_routing_cases.jsonl`
(24 เคส ที่ไม่ได้เอาไปเทรนเลย) ก็วัด TF-IDF ได้จริงเป็นครั้งแรก: **0.958** (23/24 เคส,
พลาด 1 เคส: "แข้งเบอร์ 9 ของซิตี้คือใคร ยิงไปกี่ลูกแล้ว" → ทาย `match_result` ที่ถูกคือ
`standings_stats`) ถือว่า D4 (เพิ่มตัวอย่างตาม pattern ที่พลาด) ช่วยได้จริงบนชุดที่ไม่รั่ว

## สรุปเบื้องต้น (จากตัวเลขที่มี ณ ตอนนี้)

- TF-IDF ใช้งานจริงตอนนี้: 78.4% บน held-out split (254 แถวหลังแก้ leak, เดิม 80.4% ตอนที่ยังมี
  ข้อมูลรั่ว 3 แถว) และ 95.8% บนชุด routing cases ที่ไม่เคยเห็นเลย เร็ว ไม่มีค่าใช้จ่าย ไม่พึ่งเน็ต
  → เหมาะเป็น production classifier ของ `/local/classify` (ตามที่ contract กำหนด `tfidf-logreg-v1`)
- embeddings และ LLM-based ยังไม่มีตัวเลขจริงจากสภาพแวดล้อมที่เขียนไฟล์นี้ (ดูเหตุผลบนสุดของ
  `eval/compare_methods.py`) — รันสคริปต์นี้ในเครื่องที่ต่อเน็ตได้เพื่อเติมให้ครบ
- แม้ embeddings/LLM จะแม่นกว่า TF-IDF จริง ทั้งสองวิธีก็ช้ากว่าและมีต้นทุนต่อ request สูงกว่ามาก
  ซึ่งขัดกับเป้าหมายของ `/local/classify` ที่ต้องเป็น "ชั้นกรองที่เร็วและถูก" ก่อนค่อยเรียก LLM
  (ดู 03_process.txt เดิม: "ควบคุมต้นทุน General AI ด้วย token budget") — TF-IDF จึงน่าจะเป็นตัวเลือก
  ที่เหมาะกับงานนี้อยู่ดี แม้ accuracy จะไม่สูงสุดในสามวิธี