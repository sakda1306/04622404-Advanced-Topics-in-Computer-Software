# งาน 07 — Decision and LLM Engine

ต้นแบบของงาน 07 ตาม `01_env.txt`, `02_step.txt` และ `03_process.txt`: รับหลักฐานที่เตรียมแล้ว ตรวจความสอดคล้อง เลือก action ด้วยกฎที่มีเวอร์ชัน ล็อก action และสร้างคำอธิบายพร้อมแหล่งอ้างอิง โดยเริ่มใช้ข้อความจาก template ได้ทันที

**นโยบายและสัญญาข้อมูลในโฟลเดอร์นี้เป็นฉบับทดลอง** ยังไม่ได้รับรองจากทีม และยังไม่ใช่ระบบที่อนุมัติให้ใช้ตัดสินใจการเดินทางจริง ตัวอย่างเป็นข้อมูลจำลอง ไม่ใช่ผลจาก Module 06 การตั้ง `POLICY_APPROVED=true` อย่างเดียวไม่สามารถอนุมัตินโยบาย prototype ได้

## ขอบเขตที่ทำในรุ่นนี้

- FastAPI และ Pydantic v2 สำหรับตรวจ input/output และเปิด API ให้ Module 03 ทดลองเรียก
- ตรวจว่า request, route และ travel time ของหลักฐานตรงกัน รวมถึงปัญหาคุณภาพและอายุข้อมูล
- Decision table มีเวอร์ชัน ใช้ action ตาม guide: `NORMAL`, `CHANGE_ROUTE`, `DELAY`, `AVOID`
- ให้ข้อจำกัดหรือประกาศทางการมีความสำคัญสูงสุด และไม่ตีความข้อมูลขาดว่าเส้นทางปลอดภัย
- confidence ผลลัพธ์เป็น float 0–1 พร้อมปัจจัยคำนวณและ escalation; รองรับ ordinal input เดิมจาก 03/06
- Emergency Instructions เป็นหน้าที่ของ 07: ใช้รายการคำแนะนำที่ทบทวนใน catalog และตรวจแหล่งข้อมูล พื้นที่ ประเภทภัย ภาษา และเวลา ก่อนใช้; ถ้าไม่มีจะส่ง fallback พร้อม escalation
- ข้อความ fallback จาก template และจุดเชื่อมต่อ provider สำหรับทดสอบการตรวจคำตอบ โดยยังไม่มีการเรียก LLM ภายนอกจริง
- audit trace แบบ JSONL บันทึกข้อมูลที่จำเป็นต่อการตรวจย้อนหลัง และ Docker Compose สำหรับเปิดเฉพาะ 07

รุ่นนี้ไม่ได้แก้โค้ดหรือ Compose กลางของงานอื่น ไม่มี dependency ที่บังคับให้ต้องเปิด 02–06 หรือ 08 ก่อน

## รุ่น 0.3.0: quality flags และ emergency handoff

อ่าน contract และรายการส่งต่อปัจจุบันใน [integration-v3](docs/integration-v3.md); สูตรคะแนนเดิมมีใน [integration-v2](docs/integration-v2.md).
เพิ่ม `partial`, `freshness_unknown` และ metadata ของ emergency contact ที่แยกจาก object ของ 02 พร้อมตัวช่วยส่งต่อเฉพาะ emergency ให้ 08
รุ่นนี้ใช้ `DECISION_POLICY_VERSION=prototype-v3`; หากมี `.env` เก่าต้องเปลี่ยนค่านี้ และเพิ่ม flags ใหม่ใน `ESCALATION_RULES` ตาม `.env.example`
และแนะนำ `LLM_TIMEOUT=3` เพื่อเหลือเวลาให้ HTTP/audit ภายใน timeout ต่อ tool ของ 03
ที่ประมาณ 5 วินาที ไม่ใช่งบรวม 60 วินาทีทั้ง Agent

## เริ่มใช้งานด้วย Python

ต้องมี Python 3.12 ขึ้นไปและ `uv` รันคำสั่งจากโฟลเดอร์นี้ ตัวอย่างสำหรับ PowerShell:

```powershell
Set-Location 'D:\RMUTT\Advanced Ai\TEAMD\Advanced-Topic-in-Computer-Software-Course-Team-D\DL-07-Agentic-AI-System-II\07_decision_llm_engine'
uv sync --frozen
Copy-Item .env.example .env
uv run python scripts/refresh_examples.py
uv run uvicorn decision_engine.api:app --host 127.0.0.1 --port 8050
```

คัดลอก `.env` เฉพาะครั้งแรก เพื่อไม่ทับค่าที่ปรับไว้แล้ว เปิด [API docs](http://localhost:8050/docs) เพื่อดู schema ฉบับปัจจุบันและลองส่งคำขอ

เปิด PowerShell อีกหน้าต่างจากโฟลเดอร์เดียวกันแล้วทดสอบ:

```powershell
Invoke-RestMethod http://localhost:8050/health
Invoke-RestMethod http://localhost:8050/ready
curl.exe --fail-with-body -X POST http://localhost:8050/v1/decisions -H 'Content-Type: application/json' --data-binary '@examples/low_risk.json'
```

ระบบตรวจอายุข้อมูล จึงควรรัน `uv run python scripts/refresh_examples.py` ใหม่ก่อนสาธิต เพื่อให้เวลาของชุดตัวอย่างสัมพันธ์กับเวลาปัจจุบัน การเปลี่ยน timestamp นี้ใช้กับข้อมูลจำลองเท่านั้น ห้ามเปลี่ยนเวลาเพื่อทำให้ข้อมูลจริงที่เก่าดูใหม่

## เริ่มใช้งานด้วย Docker Compose

ต้องมี Docker Engine และ Compose plugin ที่ทำงานอยู่ เช่น Docker Desktop บน Windows รันจากโฟลเดอร์ 07:

```powershell
docker compose -p teamd-07 config --quiet
docker compose -p teamd-07 up --build -d --wait
docker compose -p teamd-07 ps
docker compose -p teamd-07 logs --tail 100 decision-engine
uv run python scripts/smoke_http.py
```

Compose มีค่าเริ่มต้นครบ จึงไม่จำเป็นต้องมี `.env` และไม่ต้องมี LLM API key ใช้ `.env` เมื่ออยากเปลี่ยนค่า เช่น `DECISION_HOST_PORT=8051` ค่านี้เปลี่ยนพอร์ตบนเครื่องเท่านั้น พอร์ตภายใน container ยังคงเป็น `8050`

เปิด [API docs](http://localhost:8050/docs) หรือใช้คำสั่งทดสอบ HTTP ด้านบน หากเปลี่ยน host port ต้องเปลี่ยน URL ให้ตรงกันด้วย การสร้างตัวอย่างใหม่ผ่าน script ต้องมี Python/uv บนเครื่องแยกจากการเปิด service ด้วย Docker

```powershell
docker compose -p teamd-07 stop
docker compose -p teamd-07 start
docker compose -p teamd-07 down
```

ใช้ project name `teamd-07` เดิมทุกครั้งเพื่ออ้าง container/volume ชุดเดียวกัน `docker compose -p teamd-07 down` เก็บ named volume ของ audit ไว้สำหรับเปิดครั้งถัดไป ไฟล์อยู่ที่ `/app/data/audit.jsonl` ภายใน container ดูได้ด้วย:

```powershell
docker compose -p teamd-07 exec decision-engine python -c "from pathlib import Path; p=Path('/app/data/audit.jsonl'); print(p.read_text(encoding='utf-8') if p.exists() else 'No audit records yet')"
```

Image ติดตั้ง dependency จาก `uv.lock` ด้วย `uv sync --frozen --no-dev --no-install-project` แล้วรันด้วย user ที่ไม่ใช่ root มี `/health` healthcheck และพื้นที่เขียนเฉพาะ audit volume กับ temporary directory ไม่คัดลอก `.env` หรือข้อมูล audit เข้า image

**สถานะ Docker (19 กันยายน 2026):** เชื่อม Docker Engine ได้แล้วและ build/run container จริงสำเร็จ ดูผล API/audit และขอบเขตการทดสอบใน [implementation-status](docs/implementation-status.md)

## API และการต่อกับเพื่อนในอนาคต

| Method | Path | หน้าที่ |
| --- | --- | --- |
| GET | `/health` | ตรวจว่า process ตอบสนอง |
| GET | `/ready` | ตรวจความพร้อมตามที่ service กำหนด ไม่ใช่การรับรองนโยบายสำหรับใช้งานจริง |
| POST | `/v1/decisions` | รับหลักฐานแล้วคืนผลตัดสิน เหตุผล citation ความไม่แน่นอน และเวอร์ชันที่ใช้ |
| GET | `/docs` | เปิด OpenAPI docs และ schema |

Input ของ 07 เป็น draft contract สำหรับรับ risk, weather/transport summary, route options, RAG evidence และ data-quality report ที่เตรียมมาแล้ว 07 ไม่ดึง API ภายนอก ไม่ค้น RAG และไม่ฝึกโมเดลแทน Module 04–06 ให้ดู field จริงจาก `/docs` และ `examples/*.json`

เมื่อรวม Compose ในอนาคต Module 03 ที่อยู่ใน Docker network เดียวกันจะเรียก `http://decision-engine:8050` ส่วนโปรแกรมบนเครื่องเรียก `http://localhost:8050` ชื่อ service และ network ต้องตกลงกับทีมก่อน Compose แยกชุดไม่ได้อยู่ network เดียวกันโดยอัตโนมัติ

ชื่อ action ภายในใช้ตาม guide ของ 07: `NORMAL`, `DELAY`, `AVOID` map เป็น `TRAVEL_NORMALLY`, `DELAY_TRAVEL`, `AVOID_TRAVEL` ของ 02 และ `CHANGE_ROUTE` ใช้ชื่อเดียวกัน การส่งต่อ action ผ่าน 03 มีอยู่แล้ว ส่วน confidence/emergency และ flags ใหม่ต้องให้เจ้าของ 03/08 ต่อเพิ่มตาม `docs/integration-v3.md`

Response มี `action_code` ตาม guide และ `backend_action_code` เป็น mapping ที่เสนอไว้แล้ว แต่ไม่ได้หมายความว่า JSON ทั้งชุดเข้ากับ Backend 02 โดยอัตโนมัติ ต้องยืนยัน contract ร่วมกันก่อน

`citations` เก็บเฉพาะหลักฐานที่กฎใช้และผ่านการตรวจเวลา/ประเภท/สถานะทางการ ส่วน `evidence_status` แสดง ID และผลตรวจของหลักฐานทั้งหมด รวมถึงรายการที่ไม่ได้ใช้อ้างอิง หากหลักฐานประกาศปิดถนนเก่าหรือยังยืนยันไม่ได้ ระบบยังคงผลแบบระมัดระวังพร้อม escalation ไม่ถือว่าการตัด citation ออกทำให้ถนนเปิด

การตรวจในรุ่นนี้ตรวจโครงสร้าง ความสัมพันธ์ และ metadata ที่ผู้เรียกส่งมา ไม่ได้พิสูจน์ความแท้จริงของแหล่งข่าวผ่านเครือข่าย Endpoint ยังไม่มี service authentication จึงเปิด host port เฉพาะ loopback สำหรับพัฒนา ต้องตกลง authentication และ network access ก่อนรวมระบบ

## การตั้งค่าและกฎทดลอง

เริ่มจาก `.env.example` ค่าจำเป็นตาม guide ถูกเตรียมไว้ครบ แต่ `LLM_API_KEY` ยังว่างได้เพราะไม่มี live provider `TEMPERATURE=0`, token limits, timeout และจำนวนครั้งสูงสุดเป็นข้อกำหนดของเส้นทาง explainer สำหรับ provider ที่จะเชื่อมภายหลัง การใส่ชื่อโมเดลหรือ API key ไม่ได้เปิดการเรียก provider ให้อัตโนมัติ

นโยบายทดลองอยู่ใน `decision_engine/policies` และ template อยู่ใน `decision_engine/templates` ต้องอ่านเงื่อนไขและค่าขอบเขตในนโยบายร่วมกับ tests ก่อนปรับ กรณีข้อมูลไม่ครบหรือกำกวมอาจคืน `AVOID` พร้อม escalation เป็น fallback ของต้นแบบ ไม่ใช่การยืนยันว่ามีภัยจริง

ลำดับกฎทดลอง: ประกาศงดเดินทาง/ปิดเส้นทาง → ความเสี่ยง HIGH → ไม่มีเส้นทางปลอดภัย → ข้อมูลมีปัญหา → ทางเลือกที่ใช้ได้และมี risk level ต่ำกว่า → เวลาถัดไปที่มีหลักฐานว่าปลอดภัยกว่า → LOW และไม่มีข้อจำกัด → กรณีอื่นให้ตรวจต่อ ความเสี่ยง HIGH จะไม่ถูกลดเป็น CHANGE_ROUTE ในรุ่นนี้ แม้มีทางเลือก เพราะลำดับนี้ยังรอทีมอนุมัติ

ความสดใช้ `expires_at` ของแต่ละหลักฐานเทียบกับเวลาของ service โดยค่าตรงเวลาหมดอายุถือว่า stale และ `freshness_unknown` ยังต้องส่งตรวจต่อ confidence เป็น float ตาม policy `prototype-v3`: base = ค่าต่ำสุดของ risk/data-quality; คูณสัดส่วนองค์ประกอบที่ครบและหลักฐานที่ยังสด แล้วจำกัดคะแนนเมื่อมีปัญหา รายละเอียดอยู่ใน `docs/integration-v3.md` ไม่ได้แทน model probability

Provider seam ในรุ่นนี้ตรวจข้อความเทียบกับ sentence bank ที่อนุญาตอย่างเข้มงวด จึงยังไม่ใช่การเขียนคำอธิบายอิสระด้วย LLM ส่งออกไปเฉพาะ action ที่ล็อก ข้อความที่อนุญาต และ evidence IDs ที่ผ่านการตรวจ ไม่ส่ง raw summary/RAG excerpt งบ token ปัจจุบันใช้จำนวน UTF-8 bytes เป็นขอบเขตแบบระมัดระวัง และต้องเปลี่ยนเป็น tokenizer ของ provider เมื่อเชื่อมจริง

Audit JSONL ใช้สำหรับ API process เดียวตามคำสั่งเริ่มต้น ยังไม่มี rotation/retention worker หรือการประสานการเขียนหลาย process ไม่ควรเพิ่ม `--workers` จนกว่าจะมี shared audit storage

การเปลี่ยนนโยบายต้องผ่านการทบทวน อนุมัติ ออกเวอร์ชัน และเก็บเวอร์ชันเก่าเพื่อย้อนกลับตาม guide ขณะนี้ใช้ไฟล์ใน repository เป็นที่เก็บเวอร์ชัน ส่วนระบบจัดเก็บและกระบวนการอนุมัติเต็มรูปแบบยังต้องทำเพิ่ม ไม่ควรแก้ค่าของนโยบายเดิมแล้วใช้ชื่อเวอร์ชันเดิม

## ทดสอบ

```powershell
uv run pytest
uv run ruff check .
```

ชุดทดสอบครอบคลุมกฎและกรณีขอบเขต รวมถึงการป้องกัน explainer เปลี่ยน action หรือสร้างหลักฐานเอง ให้ใช้ผลที่รันได้จริงบนเครื่องเป็นหลัก README นี้ไม่ได้รับรองว่าการทดสอบหรือ Docker ผ่านเพียงเพราะมีคำสั่งข้างต้น

## งานที่ยังรอการตกลงหรือพัฒนาต่อ

- 03 ส่ง quality flags และ emergency_instructions แล้ว รวมถึงต่อ 05/06 จริง; ยังต้องตกลงผู้ผลิต quality confidence/active_restriction และ emergency_context จาก region ที่ยืนยันแล้ว ตาม `docs/integration-v3.md`
- เติม catalog คำแนะนำเฉพาะภัยจากเอกสารทางการที่ผ่านการทบทวน และตกลงเจ้าของข้อมูล emergency contacts; catalog ที่แจกยังไม่มีคำแนะนำเฉพาะภัยจริง
- อนุมัติเกณฑ์ความเสี่ยง ความสดของข้อมูล ความปลอดภัยของทางเลือก และลำดับกฎเมื่อหลายเงื่อนไขเกิดพร้อมกัน
- เชื่อม LLM SDK ที่รองรับ structured output พร้อมทดสอบ provider จริงและการควบคุม timeout/token/retry
- เพิ่ม Redis cache, PostgreSQL สำหรับ policy/prompt versions และ OpenTelemetry หรือ Langfuse ตาม environment ที่ guide แนะนำ; JSONL ปัจจุบันเป็น audit แบบ local ไม่ใช่ระบบ tracing ครบชุด
- ผสานกับ Compose/network/secret management ของทีม และทดสอบ health/readiness กับระบบรวม โดยไม่แก้ส่วนเหล่านั้นในงานรอบนี้

ไฟล์ guide `.txt` เดิมยังเป็นแหล่งข้อกำหนดหลักของงาน README นี้อธิบายขอบเขตของต้นแบบและวิธีใช้งาน ไม่ได้แทนข้อกำหนดใน guide
