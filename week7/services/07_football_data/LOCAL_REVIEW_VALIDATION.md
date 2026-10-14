# Local PR6 review validation — 2026-09-27

ผลตรวจรอบแก้ PR6 ก่อนเพิ่มข้อมูลย้อนหลัง ผลตรวจ API จริงและชุดทดสอบล่าสุดดูใน HISTORICAL_DATA.md

## สิ่งที่ตรวจในเครื่อง

- SQLite durable outbox: 503 แล้ว retry ใน process เดิม, backoff, กู้ transition ที่ยังไม่ถึง grace period ตอน startup ทั้ง published/draft และ shutdown worker
- Batch synthetic 438 เอกสาร (ปริมาณเทียบ 380 นัด + 38 ตารางคะแนน + 20 fixture docs): 100/100/100/100/38; batch ที่สองล้มเหลวแล้วส่งซ้ำเฉพาะ 100 เอกสารนั้น ไม่มีเอกสารซ้ำ; ไม่ใช่ benchmark ข้อมูลจริงทั้งฤดูกาล
- จำกัดขนาดตาม UTF-8 bytes และเก็บ oversized document ไว้พร้อม error
- ดาวซัลโวอยู่ใน standings search document; latest completed week และ live label; รองรับ snapshot เดิมที่ยังไม่มี label
- edit → publish ใช้ source facts ภาษาอังกฤษ ไม่เอาผลที่ admin พิมพ์ใหม่ไปแทนข้อมูลต้นทาง; backfill รายงานเก่า
- เปิดบริการ 05 จริงผ่าน uvicorn บน localhost ด้วย checkout origin/develop f0e5cb9: upsert/search ผลแข่งและดาวซัลโว, publish/search/unpublish และ 503 recovery; ใช้ FakeEmbedder ของ 05

## คำสั่งตรวจซ้ำ

รันจาก services/07_football_data (Python ใน .venv):

```powershell
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m pytest -q
$env:RETRIEVAL_TEST_ROOT = 'C:\Users\paphawit14\football-review-integration-20260927\services\05_retrieval_knowledge'
.venv/Scripts/python -m pytest -q
```

เทส HTTP 05 จะ skip หากไม่ตั้ง RETRIEVAL_TEST_ROOT; subprocess ใช้ฐานข้อมูล index ชั่วคราวและปิดเมื่อเทสจบ

ผลรอบสุดท้าย: ruff check ผ่าน, format ผ่าน 14 ไฟล์, เทสปกติ 14 passed / 1 skipped (4.75 วินาที), เปิดเทสบริการ 05 แล้ว 15 passed (7.46 วินาที), git diff --check ผ่าน มีเพียงคำเตือน LF/CRLF

## ข้อจำกัดก่อนขออนุมัติ PR

- API ฟุตบอลและ Generation ยังจำลอง ไม่มีการยืนยันข้อมูลภายนอกจริงหรือโมเดล embedding จริง
- origin/develop ที่ตรวจไม่มี services/06 จึงยังทดสอบบริการ 06 จริงไม่ได้
- ยังไม่ทดสอบ PostgreSQL, multiple workers, migration หรือ throughput ทั้งฤดูกาลจาก API จริง
- นำ workflow football-data-07.yml จาก develop มาเพิ่มโดยไม่ merge ทั้ง branch; ยังไม่มีผล GitHub CI ของการแก้ครั้งนี้จนกว่าจะ push
