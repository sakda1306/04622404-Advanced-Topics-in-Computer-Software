# PANBALL — 01 Web App

Next.js 14 + TypeScript สำหรับผู้ช่วยฟุตบอลพรีเมียร์ลีก ธีมและมาสคอส 5 ทีม อ่านข้อมูลผ่าน API Backend ของทีม 02 เท่านั้น

## ฟีเจอร์ล่าสุด — 1 ตุลาคม 2026

### Prediction / Season Lab / บริบทแชท (Contract v1.8)

- Hub เลือกแมตช์ที่กำลังแข่ง → นัดถัดไป → ผลล่าสุด พร้อมเวลาอัปเดต; เปรียบเทียบฟอร์มและประเด็นก่อนเกมเฉพาะเมื่อมีนัดถัดไป
- การ์ดทำนายก่อนแข่งเรียก `GET /api/football/predict` แสดงชนะ/เสมอ/แพ้ สกอร์ และ xG จาก backend; ไม่คำนวณความน่าจะเป็นเอง และซ่อนเมื่อ 404/422
- โอกาสทั้งฤดูกาลและหน้า `/football/simulation` ใช้ snapshot จาก `GET /api/football/simulation` พร้อมเวลาข้อมูล สถานะเก่า จำนวนการจำลอง และกราฟเลือกอันดับด้วยเมาส์/slider/แป้นพิมพ์ ตารางเปลี่ยนเป็นการ์ดบนมือถือ
- แชทมีคำถามทั่วไป 5 ข้อและคำถามทำนาย 2 ข้อ กดเพื่อเติมร่างก่อนส่ง; ส่งข้อความเดิมและ session ID ให้ backend จัดการบริบท แสดง `standalone_query` / `condense` ในรายละเอียดเมื่อ API ส่งมา
- แมตช์บันทึกแสดง 2 นัดถัดไปก่อน เปิดจัดการรายการทั้งหมดได้; ประวัติแชทด้านบนมือถือพับได้

ใช้ Compose กลางเมื่อต้องการทดสอบผลจำลองครบลีก: จาก root ของโครงการรัน `docker compose up -d --build --wait` แล้วเปิด `http://localhost:3000` โดยใช้บัญชีที่กำหนดใน root `.env` ชุด demo ของ 01 ที่ใช้ stub ของ 02 ยังส่ง simulation snapshot ไม่ครบรูปแบบ (1 ทีมแต่ position_probs มี 2 อันดับ) เว็บจะแสดงข้อผิดพลาดข้อมูลแทนการสร้างข้อมูลเพิ่มเอง ส่วน backend จริงตรวจแล้วส่งครบ 20 ทีม ดูรายละเอียดใน [TEST_RESULTS.md](TEST_RESULTS.md)

ประวัติแชทที่โหลดกลับมาจาก API ไม่มี trace จึงแสดงข้อมูล condense ได้เฉพาะคำตอบใหม่หรือหน้า admin ที่ backend ส่ง trace มาเท่านั้น

ปรับ UI ตามภาพอ้างอิงเป็นพื้นหลังสนามต่อเนื่องและการ์ด Midnight พร้อมสีทีมโปรด: Hub จัดเป็นสองคอลัมน์, ตารางคะแนนมีสรุป 5 อันดับ/ฟอร์มด้านขวา, แตะผลฟอร์มเพื่อเปิดแมตช์, โปรแกรมแข่งจัดกลุ่มตามวันเวลาไทย และตั้งค่ามีภาพตัวอย่างกับปุ่มบันทึกติดขอบล่างบนมือถือ

- หน้าแรก Matchday Hub: นัดถัดไป, ผลล่าสุด, เทียบฟอร์มสูงสุด 5 นัด และสรุปตัวเลขพร้อมลิงก์หลักฐาน/เวลาข้อมูล คำนวณจาก fixtures ที่มีในระบบโดยไม่เรียก AI
- ปุ่ม 5 ทีมด้านบนเลือกข้อมูลที่ต้องการดูเท่านั้น; ทีมโปรด ธีม และมาสคอสเปลี่ยนผ่าน **ตั้งค่าส่วนตัว** พร้อม preview, บันทึก และยกเลิก
- แชทอยู่ที่มาสคอส; เปิดได้จากประวัติ แชทใหม่ หรือปุ่มถามแพนด้า หากถามถึงทีมอื่นให้ระบุชื่อทีมในคำถาม
- บันทึกแมตช์ได้ 20 รายการต่อบัญชีในเบราว์เซอร์นี้ ไม่มีการ sync ข้ามเครื่อง
- โลโก้ครบ 20 ทีมตาม catalog ที่ตรวจ, สัญลักษณ์ฟอร์ม ✓/−/× พร้อมวงแหวนระบุนัดล่าสุด, ใช้คำว่า “นัด” และแสดงจำนวนรอบที่ทราบ
- Admin Knowledge Base รองรับ category `player`; ไม่เปลี่ยนชนิด job `weekly_report`

ข้อจำกัด: ยังใช้ API เดิม ไม่มี public teams proxy หรือ bookmarks API ใหม่; โลโก้เก็บในงาน 01 และมี fallback เมื่อไม่มีภาพ ดู [แหล่งที่มาของ assets](public/crests/ASSET.md) จำนวน 38 นัดเป็น fallback เฉพาะฤดูกาล 2026 ที่ตรวจตารางจาก 07 แล้ว; ฤดูกาลอื่นที่ไม่มี metadata ไม่เดาจำนวนรอบ สนามแสดงเฉพาะเมื่อ API ส่ง `venue` มา ดู [ผลทดสอบ](TEST_RESULTS.md) และ [แผนผลกระทบต่อโมดูล](docs/PANBALL_MODULE_IMPACT.md)

## รันด้วย Docker

จากโฟลเดอร์ `services/01_web_app`:

```powershell
docker compose build
docker compose up -d --wait
```

เปิด <http://localhost:3000> บัญชีสำหรับชุดสาธิต:

| บัญชี               | รหัสผ่านเริ่มต้น | สิทธิ์      |
| ------------------- | ---------------- | ----------- |
| demo1, demo2, demo3 | demo1234         | ผู้ใช้      |
| admin               | admin1234        | ผู้ดูแลระบบ |

Compose ชุดนี้ใช้ **Backend จริงของทีม 02 + PostgreSQL + Redis** แต่ Router และ Football Data เป็น **stub ของทีม 02** จึงมีป้ายโหมดสาธิตบนเว็บ คำตอบ/ผลฟุตบอลยังไม่ใช่ข้อมูลจริงจากบริการ 03–07

ไฟล์ Compose และ Dockerfile ทั้งหมดอยู่ในงาน 01 ตัว image สำหรับ integration อ่านและคัดลอก source ของ `../02_api_backend` โดยไม่แก้ไฟล์ต้นฉบับ ไม่ bind mount โฟลเดอร์เพื่อน การ migrate/seed ทำใน container และข้อมูลเก็บใน Docker volume `pitchside01_pgdata`

```powershell
docker compose ps
docker compose logs --tail=80 web api
docker compose down
```

`down` เก็บฐานข้อมูลไว้ การเปิดรอบต่อไป seed ไม่เปลี่ยนรหัสผ่านบัญชีที่มีแล้ว ตั้ง `WEB_PORT` ใน `.env` หาก port 3000 ถูกใช้ ค่า env สำหรับ demo อยู่ใน `.env.example` (คัดลอกเป็น `.env` ก่อนปรับได้)

## ใช้กับ API จริงของทีม

Dockerfile หลักเป็น production standalone image รันด้วยผู้ใช้ที่ไม่ใช่ root และมี `/health`:

```powershell
docker build -t pitchside-web --build-arg NEXT_PUBLIC_DEMO_MODE=false .
docker run --rm -p 3000:3000 -e API_INTERNAL_URL=http://host.docker.internal:8000 pitchside-web
```

Compose กลางจาก PR #16 อยู่ที่ [docker-compose.yml ของโครงการ](../../docker-compose.yml) แล้ว โดยตั้ง `API_INTERNAL_URL=http://api:8000` และ build เว็บด้วย `NEXT_PUBLIC_DEMO_MODE=false` ส่วน Router/Retrieval/Generation/Football Data ตั้งค่าที่ backend ตาม contract วิธีใช้อยู่ใน [คู่มือ Deploy](../../deploy/README.md) ต้องมีโค้ดบริการครบก่อนทดสอบระบบจริง การเปิดผ่าน HTTPS ต้องตั้ง `COOKIE_SECURE=true` ฝั่ง backend และใช้บัญชี/secret ของ deployment จริง

## พัฒนาโดยไม่ใช้ Docker

Node.js 22+ และ pnpm 11.25.0:

```powershell
pnpm install --frozen-lockfile
Copy-Item .env.example .env.local
pnpm dev
```

ตั้ง `API_INTERNAL_URL` ใน `.env.local` ให้ตรงกับ API Backend (ค่าเริ่มต้น `http://localhost:8000`) หากใช้ `pnpm build` แล้วต้องการเปิดผล build แบบ standalone ให้ใช้ Docker หรือ `pnpm start` สำหรับการรัน Next ในโฟลเดอร์พัฒนา

บน Windows `pnpm build` สร้างผลสำหรับ `pnpm start` โดยไม่สร้าง standalone ที่ต้องใช้สิทธิ์ symlink ส่วน Linux/Docker ยังคงสร้าง standalone สำหรับ production ตามเดิม

## หน้าจอและพฤติกรรม

| หน้า                             | ความสามารถ                                                                                                                                  |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `/login`                         | Username/password, แสดง/ซ่อนรหัสผ่าน, error จาก API                                                                                         |
| `/`                              | Chat, session/history, คำถามตัวอย่าง 5 กลุ่ม, Markdown ที่ไม่รัน HTML, citation ไป source, feedback, route ภาษาไทย, latency, เวลาไทย, trace |
| `/football/fixtures`             | ผลและโปรแกรมแข่ง กรองฤดูกาล/แมตช์วีค/ทีม/สถานะ                                                                                              |
| `/football/standings`            | ตารางคะแนนและเวลาข้อมูล                                                                                                                     |
| `/football/reports`              | รายงานที่เผยแพร่ พร้อม empty state                                                                                                          |
| `/matches/:id`                   | ผลแข่ง เหตุการณ์ ผู้เล่น สถิติ; รองรับข้อมูลว่าง                                                                                            |
| `/admin`                         | สถิติรวม, route, ชั้นตัดสินใจ, feedback, latency, fallback                                                                                  |
| `/admin/pipeline`                | สั่ง ingest/สร้างรายงาน ติดตาม queued/running/done/failed                                                                                   |
| `/admin/feedback`, `/admin/logs` | ตัวกรอง, cursor pagination, รายละเอียดคำถาม/คำตอบ/source/trace                                                                              |
| `/admin/reports`, `/admin/audit` | แก้ร่าง เผยแพร่ ถอนการเผยแพร่ และ audit                                                                                                     |
| `/admin/users`, `/admin/kb`      | ค้นผู้ใช้/เปลี่ยนบทบาท/ระงับ, สถิติคลัง/ลบเอกสารทีละรายการ/ส่งคำขอ reindex                                                                  |

API เป็นผู้บังคับสิทธิ์จริงทุกครั้ง เว็บซ่อนเมนู Admin จาก user ปกติและแสดง 403 สำหรับหน้าที่ไม่มีสิทธิ์ ไม่มี token เก็บใน localStorage

Logout/401/เปลี่ยนบัญชีล้างข้อความ session และ draft ทั้งหมด คำตอบที่ค้างจากบัญชีก่อนจะไม่เข้าบัญชีใหม่ เปลี่ยนทีมจะบันทึก preference ก่อน แล้วเริ่มบทสนทนาใหม่ เพื่อให้บริบททีมตรงกับหน้าจอ ประวัติที่โหลดไม่มี metadata ทีมจาก API จึงไม่เดาว่า session เก่าเป็นทีมใด

มาสคอสมีครบ 5 ทีม ลากได้ ใช้ Enter/Space เปิดแชทและลูกศรเลื่อนได้ บันทึกเฉพาะตำแหน่งใน localStorage รองรับ reduced motion และหยุด animation เมื่อแท็บซ่อน จำนวนเฟรมจริงแต่ละท่ากำหนดใน `lib/pet.ts`

Admin ใช้เฉพาะสถิติที่ API มี ไม่มีกราฟรายวันหรือตัวเลขเปลี่ยนแปลงที่แต่งขึ้น Reindex แสดงเพียงรับคำขอพร้อม job ID เพราะ contract ของ Web ยังไม่มี endpoint ติดตาม job ของ Retrieval ส่วน job ใน Pipeline ติดตามผ่าน `/api/admin/jobs/:id`

## ทดสอบ

```powershell
pnpm test
pnpm typecheck
pnpm format:check
pnpm build
# หลัง Docker พร้อม
pnpm test:smoke
```

Unit/component tests ใช้ Vitest + React Testing Library + jsdom ทดสอบ interaction/state รวมถึงบัญชี, citation, admin permissions, job polling และ confirmation

`test:smoke` ยิง HTTP ผ่านเว็บ Docker ไป Backend จริง ตรวจ login/cookie, แยกบัญชี, chat/history/feedback, football, Admin, publish/unpublish, 401/403/404/409/422/502/504 มีคำถาม timeout ที่ตั้งใจรอประมาณ 45 วินาที ชุดนี้จะเพิ่มประวัติ/feedback/audit ในฐานข้อมูลสาธิต และปรับสถานะรายงานใน stub จึงควรรันกับชุดสาธิตนี้เท่านั้น

ทดสอบ proxy เมื่อ API ล่ม (เปิดกลับหลังทดสอบ):

```powershell
docker compose stop api
try { node scripts/smoke.mjs --outage } finally { docker compose start api }
```

ตรวจ atlas ด้วย Python ที่มี Pillow: `python scripts/validate-mascots.py`

ดูผลที่รันจริงและขอบเขตการตรวจใน `TEST_RESULTS.md`

## เตรียมรวมระบบตาม Contract v1.3

ใช้ `pnpm check` เพื่อรัน tests, typecheck, format และ production build ตามลำดับ โดย Deploy เพิ่ม workflow [01-web](../../.github/workflows/web-01.yml) แล้วใน PR #16 ผลตรวจบน commit `e0221c1` ผ่าน: [GitHub Actions](https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D-II/actions/runs/36254446367) เมื่อส่ง commit ใหม่ต้องตรวจผลบน commit นั้นอีกครั้ง

Contract v1.3 เพิ่ม `context.last_ingest_at` ระหว่าง API 02 และ Router 03 ไม่ได้เพิ่ม field ที่เว็บต้องส่ง เว็บแสดงคำตอบและ `data_as_of` ตาม API โดยไม่ใช้เวลาสร้างข้อความแทนเวลาข้อมูล กรณี fallback ไม่มี `last_ingest_at` ต้องไม่มีเวลาที่แต่งขึ้นในคำตอบ การตรวจครบเส้นทางต้องรอ API/Router รุ่นที่รองรับ

หน้าแชทแยกคำอธิบาย `retrieval_empty` / `retrieval_down` ตาม trace และระบุเมื่อคำตอบไม่มีแหล่งอ้างอิงหรือมาจากความรู้ทั่วไป โดยไม่เปลี่ยนข้อความคำตอบจาก API หรือสร้างวันที่ขึ้นมาเอง การบังคับตอบเฉพาะข้อมูลในฐานข้อมูลต้องตกลงกับเจ้าของ Router/Retrieval/Generation ตาม Contract

หน้า error รองรับ `INDEX_NOT_READY` (503) และ `RETRIEVAL_UNAVAILABLE` (502) พร้อม Request ID และการลองใหม่ในหน้าที่รองรับ ปัจจุบัน API 02 อาจแปลงรหัสแรกเป็นรหัสหลัง

ใช้ `pnpm test:integration` สำหรับชุดทดสอบ HTTP ที่เตรียมไว้ให้ระบบจริง โดยกำหนดบัญชีทดสอบสองบัญชีและไฟล์ข้อเท็จจริงจากฐานข้อมูลก่อน ชุดนี้แยกจาก `test:smoke` ที่ใช้ stub อ่านวิธีตั้งค่า ขอบเขตการเปลี่ยนข้อมูล แผนตรวจเบราว์เซอร์ และงานที่รอทีมอื่นใน [INTEGRATION.md](INTEGRATION.md)

## ตรวจส่งมอบ PR #4

หลังรวม develop ให้รัน `pnpm install --frozen-lockfile` และ `pnpm check` แล้ว build/เปิด Docker demo จากโฟลเดอร์นี้ รัน `pnpm test:smoke` และตรวจ login, chat/history, football และ Admin ในเบราว์เซอร์ บันทึกผลและ commit ใน `TEST_RESULTS.md` เสร็จแล้วใช้ `docker compose down` โดยไม่ใส่ `-v` เพื่อเก็บข้อมูลสาธิตไว้

Peem เป็นผู้รีวิว/Approve และ Sakda เป็นผู้ merge เมื่อได้รับอนุญาตให้ส่งงาน ให้แนบ commit ล่าสุด ลิงก์ CI และผล demo smoke/browser ใน PR เดิม การทดสอบบริการจริงครบ 03–07 เป็นงานติดตามร่วมกับทีมตาม handoff และห้ามใช้ผล stub อ้างว่า integration จริงผ่านแล้ว
