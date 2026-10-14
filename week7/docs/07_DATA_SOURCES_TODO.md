# สิ่งที่ต้องเอามาสำหรับ 07 football-data

อ้างอิง: `docs/05_RETRIEVAL_DESIGN.md` §10 (ข้อมูลย้อนหลัง) และ `docs/00_PLAN_OVERVIEW.md` หัวข้อ 6 (API)

---

## 1. ข้อมูล (ข้อมูลย้อนหลัง ดาวน์โหลดครั้งเดียว ไม่ต้องใช้ key)

| สิ่งที่ต้องเอามา | ที่มา | หมายเหตุ |
|---|---|---|
| **ไฟล์ผลแข่งพรีเมียร์ลีก 34 ไฟล์** (1992/93–2025/26) | [openfootball/england](https://github.com/openfootball/england) ที่ commit `b17e8f0` · 1992/93–1999/00: `archive/1990s/<yyyy-yy>/1-premierleague.txt` · 2000/01 เป็นต้นไป: `<yyyy-yy>/1-premierleague.txt` | สัญญาอนุญาต CC0 · ไฟล์มี 3 รูปแบบ ต้องเขียน parser ให้อ่านได้ครบ (รายละเอียดใน §10.2) |
| **ตารางจบฤดูกาลทางการ** (1992/93–2023/24) | [jfjelstul/englishfootball](https://github.com/jfjelstul/englishfootball) ที่ commit `ff3c376` ไฟล์ `data-csv/standings.csv` (ใช้เฉพาะแถว `tier == 1`) | สัญญาอนุญาต CC-BY-SA 4.0 · มีคอลัมน์หักแต้ม `point_adjustment` แล้ว |
| **รายชื่อทีม** | ไฟล์ `data-csv/teams.csv` จาก repo เดียวกัน | ใช้ map ชื่อทีมของ Fjelstul |
| **ไฟล์ map ชื่อทีม → `club_slug`** | ต้องทำเองด้วยมือ | ต้องรวมชื่อที่เขียนต่างกันทั้ง 95 แบบของ openfootball ให้เหลือ 51 สโมสร พร้อมชื่อทีมของ Fjelstul และ `team_id` ของ football-data.org (ถ้ามี) |
| **`point_deductions.json`** สำหรับ 2024/25 เป็นต้นไป | ต้องทำเองด้วยมือ | Fjelstul ไม่มีข้อมูลหลัง 2023/24 จึงต้องเทียบกับตารางทางการของพรีเมียร์ลีกเอง |
| **ข้อความเครดิต** | ต้องเขียนเอง | เงื่อนไขของ CC-BY-SA: ชื่อ Joshua C. Fjelstul, Ph.D. · ลิงก์สัญญาอนุญาต · ลิงก์ repo · บอกว่าดัดแปลงอะไร |

> ⚠️ **ห้ามใช้** ไฟล์ CSV จาก football-data.co.uk ที่เคยดาวน์โหลดไว้ เว็บนั้นห้ามใช้ข้อมูลกับผลิตภัณฑ์ข้อมูล/AI และห้ามดาวน์โหลดด้วยบอต (§10.0)

---

## 2. API (ข้อมูลสดฤดูกาลปัจจุบัน ต้องใช้ key)

| API | ต้องเอามา | ใช้ทำอะไร | ข้อจำกัด |
|---|---|---|---|
| **football-data.org** v4 (แหล่งหลัก) | สมัครแล้วเอา API key | `competitions/PL/matches` · `competitions/PL/standings` · `competitions/PL/scorers` | 10 ครั้งต่อนาที ไม่จำกัดต่อวัน · ไม่มี lineups และ events |
| **API-Football** (api-sports.io, แหล่งเสริม) | สมัครแล้วเอา API key | `fixtures/events` · `fixtures/lineups` · `fixtures/statistics` เฉพาะนัดที่จบแล้ว | **100 ครั้งต่อวัน** |

- **ต้องทดสอบ API-Football ด้วย key จริงก่อน (ข้อ D1):** ดูว่าแพ็กเกจฟรีดึงข้อมูลฤดูกาลปัจจุบันได้ไหม ถ้าไม่ได้ ให้ใช้แผนสำรองในหัวข้อ 6 คือใช้ football-data.org อย่างเดียวสำหรับข้อมูลสด และใช้ API-Football กับฤดูกาลที่แล้วตอนสาธิต
- **ห้าม commit API key ลง git** ให้ใส่ไว้ใน `.env` เท่านั้น

---

## 3. ผู้รับผิดชอบ

**member5** (เจ้าของ service `07 football-data` ตาม `docs/00_PLAN_OVERVIEW.md`)
