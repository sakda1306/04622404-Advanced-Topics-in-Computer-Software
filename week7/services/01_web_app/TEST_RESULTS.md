# ผลทดสอบงาน 01 Web App

วันที่ตรวจล่าสุด: 1 ตุลาคม 2026

## เพิ่มคำแนะนำทีมโปรดก่อน merge PR #37

- แสดงการ์ดเหนือคำถามแนะนำเฉพาะผู้ใช้ login แล้วและ `favorite_team_id === null`; ปุ่มเปิด PersonalSettings ร่วมกับเมนูเดิม ร่างคำถามยังอยู่
- เปิด/ยกเลิกตั้งค่า เลือกทีมที่ดู และส่งคำถามไม่บันทึกทีมโปรดอัตโนมัติ; บันทึกสำเร็จแล้วการ์ดหาย บันทึกล้มเหลวยังคงการ์ดและ dialog
- แก้กรณีผู้ใช้ยังไม่มีทีมโปรดแต่กดบันทึกทีมเดียวกับธีมเริ่มต้น ให้เรียก preferences API เมื่อผู้ใช้ยืนยันจริง
- เพิ่ม 6 regression tests: null favorite, favorite มีค่า, guest, เปิด/ยกเลิก/บันทึกพร้อมรักษาร่าง, save failure, browse/send ไม่ PATCH preferences
- `pnpm check` ผ่าน: **92 Vitest tests + 5 Node tests รวม 97 tests**, TypeScript, Prettier และ production build
- รอบนี้แก้เฉพาะ 01; ยังไม่ commit/push และยังไม่ได้ rebuild Docker หรือตรวจ browser ใหม่สำหรับการ์ดนี้ ผล responsive/Docker ด้านล่างเป็นผลจากรอบก่อนหน้า

## รอบล่าสุด — Prediction / Season Lab / trace v1.8 / มือถือ (1 ตุลาคม 2026)

ฐาน `adbcd5e` บน `feature/01-web-mekmai4234` เปลี่ยนเฉพาะ `services/01_web_app` ยังไม่ commit/push/PR

| รายการ | ผล |
| --- | --- |
| `pnpm check` | ผ่าน **86 Vitest tests ใน 15 files + 5 Node tests = 91 tests**, typecheck, Prettier และ production build |
| Docker production | Compose กลาง build เว็บและเปิดที่ **http://localhost:3000** สำเร็จ เว็บ/API/router/football-data/engines/generation/retrieval/PostgreSQL/Redis healthy |
| Docker demo | rebuild image ของ 01, smoke ผ่าน **23 checks** รวม 12 page routes, auth/RBAC, jobs, reports, KB, 502 และ 504 โดยใช้ backend จริง + stubs ของ 02 |
| API จริงผ่าน web proxy 3000 | simulation 20 ทีม, position_probs ครบ 20 อันดับต่อทีม, จำลอง 10,000 ครั้ง, `stale=false`; predict Arsenal–Leeds ส่ง 0.4006/0.2738/0.3256 และ xG 1.291/1.135 |
| แชทต่อเนื่องจริง | ถามโอกาสแชมป์ Liverpool แล้ว “แล้วอาร์เซนอลล่ะ” ใช้ session เดิม; ตอบ Arsenal พร้อม `condense: applied`, standalone query ระบุ Arsenal และไม่มี fallback |
| Regression ใหม่ | HTTP 404/422/503, invalid probabilities, delayed response หลังเปลี่ยนทีม, stale snapshot, เปลี่ยนทีมโดยใช้ snapshot เดิม, simulation 20 ทีม/expand/retry, prompts, trace เก่า/ใหม่, saved preview 2 นัด, live/next/latest, partial failure, deep-link filters และ new-chat reset |
| Responsive browser | ตรวจ Hub/Simulation/แชท/Fixtures ที่ 390×844 และ Simulation ที่ 360×800; document ไม่ล้นแนวนอน (375/345 px หลังหัก scrollbar), ไม่พบรูปเสีย; desktop 1440×1000 ไม่ล้น |
| Mobile interactions | ประวัติแชทพับได้ แก้ช่องว่าง min-height เดิม; ผลจำลองเป็นการ์ด; กราฟเลือกอันดับด้วย slider/ArrowRight ได้; คำถามแนะนำเติมร่างก่อนส่ง; ลิงก์ Arsenal + FINISHED คงตัวกรองถูกต้อง |
| Browser logs | ไม่มี console error/warning ในรอบตรวจ production หลัง API พร้อม |

### ภาพจากเว็บจริง

ไฟล์ Git ignored อยู่ใน `node_modules/.cache/panball-qa/`:

- `prediction-docker-desktop.jpg` — Hub บน Docker/บริการจริง 1440×1000
- `prediction-docker-mobile.jpg` — Hub เต็มหน้าที่ 390×844
- `prediction-docker-mobile-card.jpg` — การ์ดทำนายและฟอร์มบนมือถือ
- `prediction-simulation-mobile.jpg` — การ์ด Arsenal/กราฟอันดับบนมือถือ (dev เชื่อม backend จริง)
- `prediction-simulation-desktop.jpg` — ภาพรวม Season Lab (dev เชื่อม backend จริง)

ทดสอบด้วยการจำลองขนาด viewport ใน desktop browser ไม่ใช่เครื่อง Android/iOS จริง และไม่ได้ยืนยัน virtual keyboard หรือ Safari เฉพาะอุปกรณ์ ภาพใช้ผลจากฐานข้อมูลท้องถิ่น/แบบจำลอง ไม่ได้ยืนยันว่าเป็นผลฟุตบอลโลกจริง

### ข้อจำกัดและการปิดงานทดสอบ

- demo stub ของ 02 ส่ง simulation 1 ทีมแต่ position_probs 2 ค่า เว็บแสดงข้อมูลไม่สมบูรณ์ตามที่ออกแบบ; backend จริงส่งครบ 20 ทีมและแสดงปกติ ไม่แก้ไฟล์ของ 02
- History API ยังไม่ส่ง trace จึงแสดง condense/standalone query ย้อนหลังไม่ได้; ข้อมูลนี้แสดงเมื่อคำตอบใหม่หรือ admin API ส่ง trace มา
- Bookmarks อยู่ใน localStorage แยก user ID สูงสุด 20 รายการ ไม่มี sync ข้ามอุปกรณ์
- รอบแรกของ typecheck พบ `exact` ที่ Testing Library ไม่รองรับใน test ใหม่ แก้แล้ว rerun `pnpm check` ผ่านทั้งหมด
- รอบแรกของ smoke หลังกลับมาทำงานต่อพบ backend ถูกหยุด (502); เปิดบริการและรันใหม่ผ่านครบ 23 checks
- คืน favorite ของบัญชี admin จาก Man City เป็น Manchester United ตามค่าเดิมหลังเก็บภาพ ไม่มีการเปลี่ยนรหัสผ่านหรือ ingest ข้อมูลใหม่; มี chat sessions จากการทดสอบ API ตามปกติ
- เปิด Compose กลางที่พอร์ต 3000 ไว้ให้ตรวจ และหยุดชุด demo `pitchside01` พอร์ต 3002 หลัง smoke test โดยเก็บ volume ไว้; ผลนี้เป็น local validation ยังไม่มี CI สำหรับการเปลี่ยนแปลงที่ยังไม่ commit

## รอบก่อนหน้า — ปรับภาพลักษณ์ตาม 5 ภาพอ้างอิง (1 ตุลาคม 2026)

ปรับพื้นหลังสนามต่อเนื่อง โทน Midnight/สีทีมโปรด เมนูและปุ่มเลือกทีม การ์ด Hub แบบสองคอลัมน์ ตารางพร้อมแผงสรุปลีกด้านขวา โปรแกรมแข่งแยกตามวัน และหน้าตั้งค่า preview ธีม/มาสคอส โดยแก้เฉพาะ 01 และยังไม่ commit/push/PR

- `pnpm check` ผ่าน: **69 Vitest tests ใน 14 files + 5 Node tests รวม 74 tests**, typecheck, format และ production build
- `docker compose build web` ผ่านบน Node 22 Alpine; อัปเดต container ด้วย `WEB_PORT=3002 docker compose up -d --no-deps --wait web` และสถานะ healthy
- `WEB_URL=http://127.0.0.1:3002 pnpm test:smoke` ผ่านครบ **23 checks** บน image ล่าสุด รวม router failure 502 และ intentional timeout 504; API/PostgreSQL/Redis จริง ส่วน AI และข้อมูลฟุตบอลใช้ stubs ของ 02
- ตรวจ browser ที่ `http://127.0.0.1:3002/` หลัง deploy: PANBALL/หน้าสรุปก่อนเชียร์/ธีมทีมโปรดแสดงได้ รูปไม่มีโหลดเสีย และไม่พบ console error/warning; เก็บภาพ `polish-docker-final.jpg` และเปิด Docker demo ที่พอร์ต 3002 ไว้ให้ใช้งานต่อ
- เพิ่ม regression tests: จัดกลุ่มวันแข่งขันตามเวลาไทยเมื่อข้ามเที่ยงคืน, ปุ่มทุกทีมอยู่นอกลิงก์แมตช์ และฟอร์มมีสกอร์/วันที่/ลิงก์รายละเอียดตรงแมตช์
- Browser ตรวจข้อมูลครบ 20 ทีมที่ 1536×1024 และ 1440×900; โลโก้โหลดครบ ตารางคะแนนไม่ล้น container ที่ 1440 และ 1536; ตรวจ Hub/Fixtures/Standings/Settings ที่ 390×844 หน้าไม่ล้นแนวนอน (ตารางยาวเลื่อนภายใน)
- ตรวจเลือกดู Arsenal ขณะใช้ธีม Man City, บันทึก/ลบ bookmark, เปลี่ยนตัวกรองจากทีมเดียวเป็นทุกทีมโดยยังคงนัดที่ 4, แผง preview ตั้งค่า, ลากมาสคอส, และ Admin; ไม่พบ console error/warning ในช่วงตรวจ
- ข้อมูลฟุตบอลครบ 20 ทีมสำหรับตรวจ layout ใช้ **synthetic QA API** ชั่วคราวในไฟล์ ignored ของ 01; อ่านชื่อ/โลโก้จาก catalog แล้วสร้างสกอร์ทดสอบ ไม่ใช่ผลฟุตบอลจริง ไม่มีการเขียนข้อมูลทดสอบนี้ลงฐานข้อมูลฟุตบอลหรือฝังใน runtime app และปิด QA server หลังตรวจแล้ว
- ภาพชุดล่าสุดอยู่ใน `node_modules/.cache/panball-qa/`: `polish-hub-desktop.jpg`, `polish-hub-mobile.jpg`, `polish-standings.jpg`, `polish-settings.jpg`, `polish-admin.jpg` (Git ignored)
- คืน favorite ของบัญชีที่ใช้ตรวจเป็นค่าเดิมและลบ bookmark ทดสอบแล้ว; ไม่อ้างว่าได้ทดสอบ integration ของบริการ 03–07 จริงครบระบบ

## รอบก่อนหน้า — PANBALL / Matchday Hub / player category

แก้เฉพาะ `services/01_web_app` ต่อจาก HEAD `d15c873` บน `feature/01-web-mekmai4234` ยังไม่ commit, push หรือส่ง PR

| รายการ | ผล |
| --- | --- |
| `pnpm check` | ผ่าน: 67 Vitest tests ใน 13 files + 5 Node tests รวม 72 tests, typecheck, Prettier และ production build บน Windows |
| `docker compose build web` | ผ่าน production standalone build บน Node 22 Alpine |
| Compose ของ 01 / port 3002 | Web, API, PostgreSQL, Redis และ 2 stubs healthy |
| `WEB_URL=http://127.0.0.1:3002 pnpm test:smoke` | ผ่าน 23 checks บน image ล่าสุด รวม 502 และ intentional timeout 504 |
| Admin `player` | Unit test ยืนยัน dropdown และ POST body `{ "category": "player" }`; ตัวเลือกทั้งหมดส่ง `{}`; browser เลือก player และได้ 202 พร้อม job ID โดย UI ไม่อ้างว่างานเสร็จแล้ว |
| ทีมที่ดู / ทีมโปรด | Browser บันทึก Man City เป็นทีมโปรดขณะดู Arsenal: ธีม/มาสคอสเปลี่ยนและ browsing ยังเป็น Arsenal; preview Liverpool แล้วกดยกเลิกยังคง Man City; tests ยืนยัน browse/send ไม่ PATCH favorite และ account reset |
| แชท | ปุ่มถามแพนด้าจาก Hub เปิด composer พร้อมชื่อทีม; ส่งคำถามผ่าน API และ router stub สำเร็จ; เริ่มแชทใหม่บนมือถือได้ |
| ฟุตบอล | Browser แสดงโลโก้, ฟอร์มพร้อมวงแหวน, “การแข่งขันนัดที่ 4 จาก 38 นัด”; ไม่มีภาพ img โหลดเสียในหน้าที่ตรวจ |
| Responsive | Spot checks Hub/ตั้งค่าส่วนตัว/Fixtures/Standings/แชท ที่ 390×844 และ Hub/Admin ที่ 1440×900; document ไม่ล้นแนวนอนในหน้าที่วัด; ตารางเลื่อนภายในได้ |
| Matchday logic | Tests ครอบคลุมนัดถัดไป, เรียง/ตัดซ้ำ/มุมมองเจ้าบ้านเยือน, cutoff, ผลไม่ครบ, สูงสุด 5 นัด, เวลาไม่ทราบ, bookmarks แยกบัญชี, storage เสีย และ empty state |
| ปิดชุดทดสอบ | ออกจากบัญชี browser แล้ว `docker compose down` เฉพาะ project `pitchside01` สำเร็จ; ไม่ใช้ `-v` จึงเก็บฐานข้อมูลไว้; ตรวจ Git แล้วไม่มีไฟล์นอก 01 เปลี่ยนแปลง |

### ข้อมูลจริงที่ตรวจในช่วงก่อนหน้าของรอบนี้

อ่าน dataset 07 ที่กำลังรันเมื่อ 30 กันยายน: season 2026 มี 20 ทีม, 380 fixtures, รอบ 1–38; นำ catalog/crest URL มาเก็บ assets ใน 01 และใช้ fallback จำนวนรอบเฉพาะฤดูกาลนี้ ทดสอบ browser ผ่าน API/บัญชีสาธิตแยกที่อ่าน football data จาก 07 ได้ โดย Hub แสดงนัด Arsenal–Leeds, ฟอร์ม/ประเด็นจาก 10 เกมอ้างอิงและผลล่าสุดได้ จากนั้นกลับมาใช้ Compose สาธิตมาตรฐานสำหรับรอบสุดท้าย ไม่มีการแก้ source ของบริการอื่น

### ขอบเขตและข้อจำกัด

- Smoke รอบสุดท้ายใช้ API 02 + PostgreSQL/Redis จริง แต่ Router/Football Data/Retrieval เป็น stub ไม่ใช่ integration บริการ 03–07 ครบระบบ และไม่ได้พิสูจน์นโยบาย database-only ของแชท
- ข้อมูล stub ณ วันที่ทดสอบไม่มีนัดในอนาคตของทีมที่เลือก จึงตรวจ empty state ใน browser; การบันทึกนัดถัดไป/แยกบัญชีตรวจด้วย component tests ไม่อ้างว่าได้ทดสอบ browser end-to-end ของ bookmarks
- 38 รอบมาจากค่าตรวจสอบเฉพาะ season 2026; เมื่อ API มี `total_matchweeks` ที่ใช้ได้จะเลือก metadata ก่อน ฤดูกาลอื่นที่ไม่ทราบไม่เติม 38 เอง
- โลโก้ local ครอบคลุม catalog ปัจจุบัน 20 ทีม; ทีมใหม่ใช้ shield fallback, ไม่ได้เพิ่ม teams API ของ 02
- ไม่เติมสนามเมื่อไม่มี `venue`; สรุปเป็นตัวเลขจาก fixtures ที่มี พร้อมบอกจำนวนข้อมูลจริง ไม่ใช่การพยากรณ์ AI
- Saved matches อยู่ใน localStorage แยก user ID สูงสุด 20 รายการ ไม่มี sync ข้ามอุปกรณ์
- ภาพ QA อยู่ใน `node_modules/.cache/panball-qa/` (Git ignored): `hub-desktop.jpg`, `hub-mobile.jpg`, `admin-player.jpg`; ภาพรอบสุดท้ายใช้ข้อมูลสาธิต
- ผลนี้เป็น local checks ยังไม่มี CI ของการเปลี่ยนแปลงที่ยังไม่ได้ commit

## รอบก่อนหน้า — ตรวจ handoff หลังรวม develop

ตรวจบน HEAD `e0221c1f79d0f30102a26e42d3190931c1ad994f` ของ branch `feature/01-web-mekmai4234` วันที่ 26 กันยายน 2026 หลังรวม Deploy PR #16 แล้ว การแก้รอบนี้มีเฉพาะเอกสาร README, INTEGRATION และ TEST_RESULTS ในงาน 01 เพื่อให้ตรงกับ CI, Compose กลาง, Contract v1.3 และขั้นตอนส่งมอบ ไม่มีการเปลี่ยน runtime code หรือไฟล์ของทีมอื่น

| รายการ | ผล |
| --- | --- |
| `pnpm install --frozen-lockfile` | ผ่าน; lockfile ไม่เปลี่ยน |
| `pnpm check` | ผ่าน 54 Vitest tests + 5 Node runner tests รวม 59 tests, typecheck, format และ production build บน Windows |
| `docker compose build` | ผ่านทั้ง Web และ API image ของ module demo |
| `docker compose up -d --wait` | ทั้ง 6 services healthy |
| `pnpm test:smoke` | ผ่าน 23 checks รวม error 502 และ intentional timeout 504 |
| Browser: Login/Chat/History | demo1 เข้าระบบ ส่งคำถามใหม่ เปิด citation แล้ว focus อยู่ที่ source ถูกต้อง; เริ่มแชทใหม่และเปิดประวัติกลับมาได้; ส่ง follow-up ความรู้ทั่วไปแล้วแสดงข้อความว่าไม่ได้ยืนยันจากคลังฟุตบอล |
| Browser: บัญชีและฟุตบอล | Logout แล้วเข้า demo2 ไม่พบประวัติทดสอบของ demo1; ตารางคะแนนแสดงข้อมูลและเวลาอัปเดต |
| Browser: Admin | admin เข้าระบบ เปิด Dashboard และ Knowledge Base โหลดข้อมูลได้; ออกจากระบบเมื่อจบ |
| GitHub `01-web` CI | SUCCESS บน commit `e0221c1`; [ดู run](https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D-II/actions/runs/36254446367) ผลนี้ยังไม่รวมเอกสารที่ไม่ได้ commit ในรอบนี้ |
| ปิด demo | `docker compose down` สำเร็จ โดยไม่ใช้ `-v` และไม่ลบ volumes |

หลักฐานภาพ Admin อยู่ใน `.next/qa-handoff-admin.png` เป็นไฟล์ QA ชั่วคราวที่ Git ignore และอาจถูกลบเมื่อ build ใหม่ รอบนี้ไม่ได้ตรวจ responsive ทุก breakpoint ซ้ำ

ข้อจำกัด: Docker และ browser ใช้ API 02/PostgreSQL/Redis จริง แต่ Router และ Football Data เป็น stub ของ 02 จึงไม่ยืนยัน integration ของบริการ 03–07 จริง หรือ database-only answers; ยังไม่ได้รัน `pnpm test:integration` กับ Compose กลาง ข้อมูลประวัติจาก API ไม่มี trace/data_as_of จึงไม่อ้างว่าทดสอบการคืน metadata เหล่านี้จาก history ได้ Smoke และ browser เพิ่ม/เปลี่ยนข้อมูลสาธิตตามชุดทดสอบ

การส่งมอบ: Peem เป็นผู้ review/approve และ Sakda เป็นผู้ merge; เมื่อได้รับอนุญาตส่งงาน ให้แนบ commit ใหม่พร้อม CI ของ commit นั้นและผลทดสอบนี้ การรวมบริการจริงเป็นงานติดตามร่วมกับทีม รอบนี้ยังไม่ commit, push หรืออัปเดต PR

## ผลรอบก่อนหน้า — เตรียมรวมระบบตามรีวิว

ทดสอบการเปลี่ยนแปลงต่อจาก `a5df132` บน branch `feature/01-web-mekmai4234` และแก้เฉพาะ `services/01_web_app` ไม่มีการเพิ่ม workflow ส่วนกลางหรือแก้บริการของทีมอื่น

| รายการ | ผลรอบล่าสุด |
| --- | --- |
| `pnpm test` | ผ่าน Vitest 54 tests ใน 11 files และ Node test runner 5 tests รวม 59 tests |
| `pnpm typecheck` | ผ่าน |
| `pnpm format:check` | ผ่าน หลังจัดรูปแบบไฟล์ทดสอบ |
| `pnpm build` บน Windows / Node 24.19.0 | ผ่าน หลังแก้ปัญหา standalone symlink (`EPERM`); Windows ใช้ `pnpm start` |
| `docker compose build web` / Node 22 Alpine | ผ่าน รวม frozen-lockfile install และ production standalone build; ทดสอบซ้ำหลังแก้ config Windows |
| `docker compose up -d --wait api` | API, PostgreSQL, Redis และ stub services เริ่มทำงานได้ |
| `docker compose up -d --no-deps --force-recreate --wait web` | เว็บ image ที่แก้ UI เริ่มทำงานและ healthy |
| `pnpm test:smoke` | ผ่าน 23 checks รวม router failure 502 และ intentional timeout 504 |
| Browser จริง | Login/logout ด้วย demo1 และ admin; เปลี่ยน 5 ทีมบนมือถือ; แชทความรู้ทั่วไปแสดงคำอธิบายใหม่; citation โฟกัส source ถูกต้อง; Admin Dashboard และ KB โหลดข้อมูลได้ |
| Responsive spot checks | Login/Chat/Admin ที่ 390×844 และ Chat/Admin ที่ 1440×900; หน้าที่วัด document width ไม่ล้น viewport; ไม่ใช่การตรวจทุกหน้าทุก breakpoint |

การแก้ไขรอบนี้เพิ่มข้อความแยก retrieval ว่าง/ไม่พร้อม, คำตอบไม่มี sources และ general knowledge โดยคงข้อความ API เดิม; รองรับ error `INDEX_NOT_READY`/`RETRIEVAL_UNAVAILABLE`; เพิ่ม regression tests ของ sources/timestamps/KB acceptance/recovery; เพิ่ม `pnpm check`, HTTP integration runner และเอกสาร `INTEGRATION.md`

ข้อจำกัดของผลรอบนี้:

- Docker ใช้ API 02 + PostgreSQL/Redis จริง แต่ Router/Football Data ยังเป็น stub ของ 02; คำตอบและผลฟุตบอลใน browser เป็นข้อมูลสาธิต
- 5 tests ของ integration runner ใช้ข้อมูลสังเคราะห์เพื่อตรวจว่าตัวตรวจจับข้อผิดพลาดได้ ไม่ใช่ผล `test:integration` ต่อ 03–07 จริง
- ยังไม่ได้รัน `pnpm test:integration` กับ Compose กลาง เพราะยังไม่มีบริการครบและชุดข้อมูลจริงที่ยืนยันสำหรับ expected facts
- `INDEX_NOT_READY` ตรวจด้วย component/proxy tests; API 02 ปัจจุบันแปลงเป็น `RETRIEVAL_UNAVAILABLE` จึงไม่อ้างว่ารหัส 503 ผ่านบริการจริงครบเส้นทางแล้ว
- UI ไม่ได้บังคับ database-only หรือพิสูจน์ความจริงจากการมี citation; นโยบาย Router/Generation ยังต้องตกลงกับทีม
- Smoke เพิ่ม chat/feedback/audit และเปลี่ยนสถานะข้อมูลสาธิตตามขอบเขต script เดิม; browser ทดสอบด้วยบัญชีสาธิตและออกจากระบบหลังตรวจ
- ณ รอบก่อนหน้านี้ยังไม่มี CI check run บน GitHub; ปัจจุบัน Deploy เพิ่ม workflow แล้วและผลล่าสุดอยู่ในหัวข้อ handoff ด้านบน

## ผลรอบก่อนหน้า — ก่อนเตรียม integration

## ขอบเขตการเปลี่ยนแปลง

แก้ไขเฉพาะ `services/01_web_app` รวมหน้า Login, Chat, Football, Admin, มาสคอส 5 ทีม, API proxy, Docker และชุดทดสอบ ไม่มีการแก้ไข source ของทีมอื่น Docker integration อ่าน source ของทีม 02 เพื่อสร้าง image API สำหรับทดสอบ

## ผลตรวจ

| คำสั่ง | ผล |
| --- | --- |
| `pnpm test` | ผ่าน 41 tests ใน 10 files หลังแก้ account/history/team/match regressions |
| `pnpm typecheck` | ผ่าน |
| `pnpm format:check` | ผ่าน |
| `docker compose build web` | ผ่าน production build |
| `docker compose up -d --wait` | เริ่มระบบสำเร็จ |
| `docker compose up -d --no-deps --force-recreate --wait web` | สร้างเว็บ container ใหม่จาก image ล่าสุด และ health check ผ่าน |
| `pnpm test:smoke` | ผ่าน 23 integration checks |
| `node scripts/smoke.mjs --outage` ขณะหยุด API | ผ่าน 1 check: 502 Problem JSON และ request ID (ทดสอบในรอบก่อนหน้า) |
| `python scripts/validate-mascots.py` | ผ่าน atlas ทั้ง 5 ทีม (ทดสอบในรอบก่อนหน้า) |
| `git diff --check` | ผ่าน ไม่มี whitespace errors |

## สิ่งที่ชุดทดสอบครอบคลุม

- ล้างข้อมูลเมื่อ logout, cookie หมดอายุ หรือเปลี่ยนบัญชี; ป้องกันคำตอบค้างจากบัญชีเก่า
- โหลด session/history, ส่งข้อความต่อใน session เดิม, เก็บ draft เมื่อส่งล้มเหลว
- บันทึกทีมก่อนเปลี่ยนบริบทและเติมคำถามตัวอย่างลงช่องพิมพ์
- Markdown, citation ที่ตรงกับ source, ป้องกัน HTML และ URL ที่ไม่ปลอดภัย
- Feedback retry เฉพาะกรณี message ยังไม่พร้อม และจำกัดจำนวนครั้ง
- API proxy ส่ง cookie/request ID และแยก 502, 504, 429
- มาสคอสใช้งานด้วยคีย์บอร์ดและจำกัดตำแหน่งให้อยู่ใน viewport
- Football filters, รายงานว่าง และข้อมูล match ที่เป็น null
- Club Edition: เลือกแมตช์ถัดไปของทีมที่ถูกต้อง และเรียงอันดับใน League Snapshot
- Logout/Login: รอ Logout จบก่อนส่ง Login และรวมการกด Logout ซ้ำเป็นคำขอเดียว ทดสอบ success, 502, 504 และ network failure; หน้า Login ปิดปุ่มและแสดงสถานะระหว่างรอ
- History: ล้าง session ที่ตอบ 404; บล็อกการส่งเมื่อโหลดล้มเหลวชั่วคราวและเปิดให้ลองใหม่; คำตอบ history เก่าไม่เขียนทับแชทใหม่
- Team preference: บันทึกไม่สำเร็จยังคงทีมและบทสนทนาเดิม; ข้อผิดพลาดแสดงบนหน้าแรก, Football และ Admin แม้ไม่มีมาสคอสเปิดอยู่
- Match preview: LIVE มาก่อน SCHEDULED ในอนาคต แล้วจึง FINISHED ล่าสุด; ข้าม POSTPONED, CANCELLED และวันที่ไม่ถูกต้อง
- Admin permissions, job polling, ยืนยันการเปลี่ยนแปลง, ป้องกันการเผยแพร่ร่างที่ยังไม่บันทึก
- HTTP ผ่าน Docker: 11 page routes, mascot assets, login/logout, favorite team, chat/history/feedback, football, admin statistics, pipeline, reports, logs/audit, users และ KB
- จงใจจำลอง router ล้มเหลวและ timeout เพื่อยืนยัน HTTP 502/504

## สภาพแวดล้อมและข้อจำกัด

- เว็บเปิดที่ <http://localhost:3000> ใช้ production image ของ Next.js
- API Backend ของทีม 02, PostgreSQL และ Redis ทำงานจริงใน Docker
- Router และ Football Data ใช้ stub ของทีม 02: ผลนี้ยังไม่ยืนยันการเชื่อม AI, Retrieval, Generation และข้อมูลฟุตบอลจริงของทุกทีม
- Unit/component tests ใช้ jsdom; ยังไม่ได้ตรวจภาพและ responsive layout ด้วย browser จริง
- Smoke test เพิ่มข้อมูล demo เช่น chat, feedback และ audit และเปลี่ยนสถานะรายงานใน stub ควรใช้กับชุด Docker สาธิตนี้
- Reindex ตรวจเพียงการรับคำขอและ job ID ไม่ได้ยืนยันการสร้างดัชนีจริงเสร็จสมบูรณ์

ดูวิธีเริ่มระบบ บัญชีสาธิต และคำสั่งทดสอบซ้ำใน [README.md](README.md)
