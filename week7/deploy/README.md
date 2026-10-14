# ส่งต่องาน 08 Deploy — Atikorn

Compose ที่ root ใช้บริการจริงตามแผนของทีม ทุกบริการคุยกันด้วยชื่อในเครือข่าย Compose และเปิด port ให้เครื่องเจ้าของงานเฉพาะ Web กับ API เท่านั้น ไฟล์ Compose จำลองในโมดูล 01 ไม่ใช่หลักฐานว่าระบบจริงเชื่อมครบแล้ว

## วิธีรัน

1. คัดลอก `.env.example` เป็น `.env` แล้วเปลี่ยนรหัสฐานข้อมูล, JWT, admin และ demo ใช้รหัสฐานข้อมูลที่ปลอดภัยสำหรับ URL เพราะค่านั้นอยู่ใน SQLAlchemy URL
2. Linux/macOS: รัน `make up`, `make smoke`, `make warmup`, `make logs`, `make down` ที่ root ของ repo บน Windows PowerShell ใช้ `./deploy/tasks.ps1 up` และเปลี่ยนชื่องานตามต้องการ
3. `warmup` ต้องมี `FOOTBALL_DATA_API_KEY` และจะดึง fixtures เท่านั้น ยังไม่สร้างหรือเผยแพร่รายงานประจำสัปดาห์ `smoke` ตรวจ health ของ 7 บริการและสิทธิ์ guest/demo/admin ยังไม่ได้พิสูจน์คำตอบครบ 5 route หรือความถูกต้องของข้อมูล

   **หมายเหตุ:** `warmup` เป็นคำสั่งที่คนสั่งรันเอง แต่ job history และหน้า Admin Pipeline จะแสดง `triggered_by: "beat"` เพราะ CONTRACT §7 ยังรับเพียง `beat` หรือ `admin:<user_id>` รายการ `beat` จาก warmup จึงไม่ใช่หลักฐานว่า Celery beat เริ่มงานตามเวลา
4. หลัง PR ของทุกบริการเข้า `develop` ให้ใช้ `pnpm test:integration` ของ Web กับชุดข้อมูลทดสอบที่ตรวจจากฐานข้อมูลจริง ตาม `services/01_web_app/INTEGRATION.md` บันทึก commit ของทั้ง 7 บริการ เวลา snapshot ของข้อมูล และผลผ่าน/ไม่ผ่านจริง ตรวจ 5 route, admin pipeline และวงจรรายงาน ก่อนสาธิตหรือรวมเข้า `main`

ณ 2026-09-26 `develop` มีบริการ 02 และ 05 เท่านั้น โค้ดของ 01/03/06/07 ยังอยู่ใน PR ส่วนเจ้าของ 04 ยังใช้ `services/04_ai_model_selection` ซึ่งต้องย้ายเป็น `services/04_ai_engines` ตามแผนก่อน build ได้ เครื่อง Windows ที่ทำงานนี้ไม่มี Docker และ Make จึงยังไม่ได้รัน Compose จริง

## CI และการรวมงาน

Workflow ใหม่ตรวจ 01/03/04/07 ตามคำสั่งทดสอบของเจ้าของโมดูล PR ของ 06 เพิ่ม `generation-06.yml` เองใน commit `a1d884e` แล้ว จึงไม่สร้างไฟล์ชื่อซ้ำใน branch นี้ Workflow 08 ตรวจไวยากรณ์ Compose และสคริปต์ แต่ยัง build/test บริการที่ไม่ได้ merge ไม่ได้ เมื่อ workflow นี้เข้า `develop` ให้ rerun CI ของทุก PR ที่ commit ล่าสุด แล้วทดสอบ Compose และ Web integration กับข้อมูลจริง ผลจาก stub ไม่นับเป็นผลระบบจริง

ตาม `docs/GIT_FLOW.md` Sakda (`sakda1306`) เป็นผู้กด merge เข้า `develop` หลัง review ตามเจ้าของโฟลเดอร์และ CI ผ่าน Atikorn เปิด PR งานนี้และประสานทดสอบเชื่อมระบบ ห้าม push เข้า `develop` โดยตรง
