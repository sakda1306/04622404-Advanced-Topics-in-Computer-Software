# หลักฐาน Smoke Test บน LLM Provider จริง — โมดูล 06

> อ้างอิงตาม `docs/CONTRACT.md` §8

## ข้อมูลการรัน

- วันที่/เวลา: 26 ก.ย. 2026 (รันซ้ำหลังแก้ injection blocking: commit `d27d5de` ขึ้นไป)
- ผู้รัน: cira1234
- Commit ที่ทดสอบ: `d27d5de` (จุดที่แก้ injection blocking pre-LLM เสร็จแล้ว)
- Provider หลักที่ใช้: Groq (model: `openai/gpt-oss-120b`)
- Fallback ที่ตั้งไว้: Gemini — **ยังไม่ได้ทดสอบ** (ไม่มี `GEMINI_API_KEY` ในทีมตอนนี้)
- `LLM_MOCK`: false
- Mode ที่ทดสอบ: `/generate` (grounded + passthrough), `/report/weekly`
- วิธีรัน: `python scripts/smoke_test_runner.py` ยิงครบ 14 เคสจาก `curl_tests/cases/`

## ผลลัพธ์ (จากการรันจริงกับ Groq)

| เคส | Endpoint | Status | เวลา (s) | Model | Token usage (in/out) | Safety blocked |
|---|---|---|---|---|---|---|
| 01_grounded_normal | /generate | 200 | 0.78 | openai/gpt-oss-120b | 804/56 | False |
| 02_grounded_insufficient_empty_context | /generate | 200 | 0.0 | none | 0/0 | False |
| 03_grounded_gambling_blocked | /generate | 200 | 0.0 | none | 0/0 | True |
| 04_grounded_two_matches_same_chunk | /generate | 200 | 0.75 | openai/gpt-oss-120b | 829/44 | False |
| 05_grounded_duplicate_ref_422 | /generate | 422 (ตั้งใจ) | 0.01 | - | - | - |
| 06_grounded_injection_attempt | /generate | 200 | 0.01 | none | 0/0 | True |
| 07_passthrough_same_language_no_llm | /generate | 200 | 0.0 | none | 0/0 | False |
| 08_passthrough_needs_translation | /generate | 200 | 0.5 | openai/gpt-oss-120b | 197/39 | False |
| 09_passthrough_gambling_blocked | /generate | 200 | 0.0 | none | 0/0 | True |
| 10_passthrough_draft_empty_422 | /generate | 422 (ตั้งใจ) | 0.0 | - | - | - |
| 11_report_weekly_full | /report/weekly | 200 | 0.99 | openai/gpt-oss-120b | 432/191 | - |
| 12_report_weekly_postponed | /report/weekly | 200 | 0.48 | openai/gpt-oss-120b | 391/107 | - |
| 13_report_weekly_empty_matches_422 | /report/weekly | 422 (ตั้งใจ) | 0.0 | - | - | - |
| 14_report_weekly_list_lineups_statistics | /report/weekly | 200 | 0.89 | openai/gpt-oss-120b | 399/249 | - |

สรุปเวลา: เคสที่ช้าที่สุดคือ 01_grounded_normal ที่ 0.78s เทียบ deadline 22s (เหลือ margin มาก) และ 11_report_weekly_full ที่ 0.99s เทียบ deadline 55s — ผ่านทุกเคสสบายๆ

เคส injection (06): ก่อนแก้ safety.blocked=False (รั่ว) หลังแก้ model=none, token=0, blocked=True — บล็อกก่อนเรียก LLM สำเร็จ ไม่พึ่งพาพฤติกรรมของ LLM แต่ละตัวอีกต่อไป

## สถานะ integration กับ 07 (Football Data) และ 03→05→06 (Router→Retrieval→Generation)

ยังไม่มีหลักฐานการต่อกับ service จริง — ที่ทดสอบมาทั้งหมดใช้ fixture ใน curl_tests/cases/ ซึ่งจำลองโครงสร้าง payload ตาม api_football.py และ CONTRACT.md §5 แต่ไม่ใช่การเรียก service 07/03/05 ที่รันจริงแบบ end-to-end

ข้อจำกัด: ทีม 03 (Router) และ 05 (Retrieval) ยังอยู่ระหว่างทำงานคู่ขนาน ยังไม่มี environment ที่รันทั้ง 4 service (03/05/06/07) พร้อมกันในเครื่องเดียว

แผนทดสอบร่วม (เสนอ):
1. เมื่อ 07 มี endpoint ที่รันได้จริง (ไม่ใช่แค่ mock) เรียก endpoint นั้นจริง เอา response จริงมายิงเข้า /report/weekly แทน fixture
2. เมื่อ 03/05 พร้อม ตั้ง docker compose รวม 4 service ตามที่ README.md หลัก (ลำดับแก้ไขร่วมกัน ข้อ 3) แนะนำไว้ แล้วทดสอบคำถามจริงข้าม service
3. จะอัปเดตไฟล์นี้พร้อมหลักฐานใหม่ทันทีที่ทำได้

## สรุปสำหรับ reviewer

- [x] ผลทดสอบ mock + provider จริง (Groq) ครบ 14 เคส พร้อมตัวเลขจริง
- [x] เคส injection ยืนยันแก้แล้วด้วยผลจริงจาก provider จริง (ไม่ใช่แค่ mock)
- [ ] Fallback (Gemini) ยังไม่ได้ทดสอบ ไม่มี key
- [ ] Integration กับ 07/03/05 จริงยังไม่มี ระบุแผนไว้ด้านบน รอ environment พร้อม
