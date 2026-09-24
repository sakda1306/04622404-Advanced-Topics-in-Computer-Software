# สถานะการทำตาม guide — Module 07

ตรวจเมื่อ 19 กันยายน 2026 รุ่น 0.3.0 / policy `prototype-v3` / output schema `07-draft-v3`

ตรวจซ้ำ 20 กันยายน 2026: เปิด service 07 กลับขึ้นมาหลัง Docker Engine พร้อมใช้งาน; container healthy และ HTTP smoke ผ่านครบ 14 สถานการณ์ พร้อม health/ready/OpenAPI และ invalid-input 422 อีกครั้ง

ตรวจซ้ำ 21 กันยายน 2026 หลัง 03/05/06 อัปเดต: เพิ่ม contract tests แบบอ่านโค้ด sibling จริง ตั้งแต่ 05 สร้าง coverage, 06 ประเมิน risk/routes, 03 สร้าง DecisionRequest จน 07 ตอบ API โดยไม่แก้ไฟล์ของโมดูลอื่น ผลยืนยันว่า complete coverage ให้ risk LOW ได้ และ 07 ตอบ NORMAL เมื่อ quality confidence เป็น HIGH พร้อม `active_restriction=false`; หากสองค่านี้ยังไม่ยืนยัน, coverage เป็น partial หรือ risk เป็น HIGH ระบบคง AVOID พร้อมเหตุผลตาม policy ชุดเต็มผ่าน 115 tests, lint/format ผ่าน และ Docker HTTP smoke 14 สถานการณ์ผ่านอีกครั้ง

| ข้อกำหนด | สิ่งที่มีในต้นแบบ | ขอบเขตที่ยังรอ |
|---|---|---|
| Python 3.12, FastAPI, Pydantic | `pyproject.toml`, `uv.lock`, `decision_engine/api.py`, `models.py` | ยืนยัน draft contract กับ 03/06/08 |
| รับหลักฐาน risk/weather/transport/routes/RAG/quality | `DecisionRequest` มีข้อมูลแต่ละส่วนและ evidence package | ข้อมูลจริงจาก 04–06; RAG excerpt ไม่ถูกใช้สร้างคำสั่งอิสระ |
| ตรวจ request/route/time | ตรวจทุก scoped input ให้ตรงกับ context กลาง | ความแท้จริงของข้อมูลต้องรับประกันจากระบบต้นทาง |
| deterministic policy | `policies/prototype-v3.json`, `policy.py`; เก็บไฟล์ v1/v2 เดิมโดยไม่เปลี่ยน | อนุมัติลำดับกฎ เกณฑ์ risk และข้อยกเว้น |
| official warnings first | ประกาศปิด/งดเดินทางชนะกฎอื่น; caution ส่งตรวจต่อ | mapping ประกาศจริงกับระดับข้อจำกัด |
| confidence/escalation | float 0–1 + confidence_details; รับ ordinal input เดิม; threshold < 0.5; เพิ่ม partial/freshness_unknown และเหตุผลส่งตรวจต่อ | ไม่ใช่ probability calibration; 03 ต้องรับ flags ใหม่ |
| Emergency Instructions | object ตาม strict schema ของ 02; local catalog + URL/hash/scope/time validation; fallback ไทย/อังกฤษ; optional metadata แยกระดับบน และตัวช่วยแปลงส่วน emergency สำหรับ 08 | ยังไม่มีเอกสาร/เบอร์ฉุกเฉินจริงใน catalog; 03/08 ต้องต่อ field ใหม่และตกลง directory policy |
| lock action before LLM | `Decision` immutable; provider ได้สำเนาของ package; ตรวจ action ซ้ำ | ประเมินกับ LLM จริง |
| grounded structured explanation | sentence bank ภาษาไทย/อังกฤษ, schema, allowlist citations | ยังไม่มี live SDK/provider และยังไม่รองรับ free-form explanation |
| timeout/token/retry/fallback | จำกัดเวลาและ attempts; byte budget; fixed template | ใช้ tokenizer ของ provider เมื่อเชื่อมจริง |
| prompt injection / secrets | ไม่ส่ง raw evidence/summary หรือ API key ให้ provider seam; ไม่ echo request ใน 422 | ทดสอบ provider จริงและระบบ authentication |
| version metadata | policy version + SHA256, prompt/model/data versions | approved policy registry, retention และ rollback workflow เต็มรูปแบบ |
| audit trace | JSONL เฉพาะ correlation ID, rules, evidence IDs/status, versions และผล validation | PostgreSQL/shared storage, rotation, access control, retention |
| Redis / PostgreSQL / tracing | แยกขอบเขตไว้ ยังไม่บังคับใช้งานในต้นแบบ | ทำเมื่อออกแบบ infrastructure ร่วมกับทีม |
| golden/property/red-team tests | 115 tests ผ่าน รวม quality flags, emergency metadata/expiry/handoff และ contract path 05→06→03→07 | live provider และ end-to-end ผ่าน service/process ของทุกโมดูล |
| Docker | build/run จริงผ่าน; nonroot UID 10001, loopback 8050, healthcheck, audit volume; restart แล้วยังอ่าน audit เดิมได้ | ยังไม่ได้เปิดบริการของเพื่อนหรือทดสอบ network รวม |

## ผลตรวจที่ทำแล้ว

- ใช้ environment Python 3.12.14 เดิม; อัปเดต lock metadata ของ project เป็น 0.3.0 แบบ offline ตรวจเทียบแล้วไม่เปลี่ยน dependency versions
- Ruff lint ผ่าน และ formatting ผ่าน
- pytest ผ่าน 115 tests ไม่มี skip บน checkout นี้; มี deprecation warnings 2 รายการจาก Starlette/httpx/AnyIO ใน dependency ชุดที่ล็อกไว้
- Docker Engine 29.8.0 และ Compose 5.5.1; `docker compose -p teamd-07 config --quiet` และ `up --build -d --wait` ผ่าน
- `scripts/smoke_http.py` เรียก HTTP จริงเข้า container ผ่าน `/health`, `/ready`, OpenAPI และ `/v1/decisions` ครบ 14 สถานการณ์จำลอง พร้อมตรวจ numeric confidence, policy digest, fallback และ input ผิดถูกปฏิเสธด้วย 422
- ตรวจ audit ใน volume ของ container: คำขอที่สำเร็จถูกบันทึก, policy v3 ตรงกัน, รันด้วย UID 10001; SHA256 ของ audit เหมือนเดิมก่อนและหลัง restart และ `/ready` กลับมาตอบ ready
- อ่านและ compile เฉพาะ model declarations จริงของ 02/08 เพื่อตรวจ emergency object และ contact fragment จากผล grounded สังเคราะห์ ไม่ได้เปิดบริการของเพื่อน และไม่ใช่ end-to-end ทั้งระบบ
- `tests/test_live_pipeline_contract.py` เรียก implementation จริงของ 05/06 และตัวสร้าง request จริงของ 03 ด้วย canonical records สังเคราะห์ ตรวจครบ 4 กรณี: quality ยังไม่ยืนยัน, LOW พร้อมใช้, HIGH และ partial coverage ไม่มีการเรียก provider ภายนอกหรือแก้ไฟล์ sibling
- เพิ่ม request examples: partial, freshness_unknown, summary_only_risk, partial_alternative; สร้าง `examples/emergency_fallback_response.json` จาก container รุ่นปัจจุบัน
- ตรวจ Git diff: guide ทั้งสามไฟล์และ policy v1/v2 ไม่เปลี่ยน; การเปลี่ยนแปลงทั้งหมดอยู่ภายในโมดูล 07 ไม่มี commit/push/merge

## สถานะที่ส่งมอบและข้อจำกัด

เปิด container `teamd-07-decision-engine-1` ไว้บน `http://127.0.0.1:8050` พร้อมให้ลอง `/docs` ใช้คำสั่งใน README โดยใส่ `-p teamd-07` ทุกครั้งเพื่อควบคุมชุดเดิม ไม่มีการแตะ container ของงานอื่น

การทดสอบรอบนี้ใช้ pytest/tmp_path ปกติได้แล้ว ไม่ใช้ workaround จากรอบ sandbox เดิม โฟลเดอร์ cache ที่กันออกด้วย ignore ไม่ใช่ไฟล์ guide หรือ artifact ที่จะส่งขึ้น Git

ผลผ่านรับรองเฉพาะต้นแบบ 07 ในขอบเขตที่ทดสอบ 03 ส่ง quality flags และ emergency object แล้ว และต่อ 05/06 จริงแล้ว แต่ 05 ยังไม่ส่ง quality confidence/active_restriction ที่ยืนยันแล้ว ทำให้ 03 ใช้ LOW/None และ 07 ตอบ AVOID อย่างตั้งใจในกรณีนั้น weather/route candidates ของ 03 ยังเป็น mock และยังต้องตกลง emergency region/catalog ไม่มี live LLM, live RAG retrieval หรือข้อมูลภัย/เบอร์ฉุกเฉินจริงในชุดทดสอบ ดูรายการส่งต่อใน `integration-v3.md`
