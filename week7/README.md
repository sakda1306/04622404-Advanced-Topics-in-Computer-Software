# Week 7 — Team D-II: Football Assistant (DL-06: Agentic AI System I)

> **Team repository (source of truth):** https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D-II
>
> This folder is a snapshot copy of the team repository (`main` @ `349af5a`, no git history). It is kept here for submission. Full history and all contributors are in the team repository.

## My part (Sakda Baokham)

Team D-II builds a Premier League football assistant (DL-06: Agentic AI System I). My roles were **team lead / coordinator**, **API Backend owner (module 02)** and **Retrieval owner (module 05)**.

### 1. API Backend — module 02 (`services/02_api_backend`)
- FastAPI gateway (`api`, `worker`, `beat`): authentication, session and conversation history, calls to the router, Celery beat for scheduled jobs.
- User data / context (users, favourite team, history), response log, feedback, stats and admin audit, all inside the API service.
- Reused and adapted the API Backend design from week 6 (see [`docs/00_PLAN_OVERVIEW.md`](docs/00_PLAN_OVERVIEW.md)).

### 2. Retrieval — module 05 (`services/05_retrieval_knowledge`)
- Hybrid search (BM25 + FAISS + RRF) with filters by season / matchweek / team / category, built on the RAG work from week 4 and corrected after week 5.
- Knowledge base: trivia corpus plus live-data documents produced by the football-data service; retrieval evaluation (hit@1 / hit@5 / MRR) in `eval/`.
- Design document: [`docs/05_RETRIEVAL_DESIGN.md`](docs/05_RETRIEVAL_DESIGN.md).

### 3. Coordination
- Wrote the team workflow ([`docs/GIT_FLOW.md`](docs/GIT_FLOW.md)), plan ([`docs/00_PLAN_OVERVIEW.md`](docs/00_PLAN_OVERVIEW.md)) and API contract register ([`docs/CONTRACT.md`](docs/CONTRACT.md)).
- Reviewed and merged teammates' pull requests into `develop` and released to `main`.

---

# Team D-II — DL-06: Agentic AI System I · ผู้ช่วยฟุตบอล (Football Assistant)

โปรเจกต์กลุ่มวิชา Advanced Topics in Computer Software (04622404)

ผู้ช่วย AI ตอบคำถามเรื่องฟุตบอล Premier League — ความรู้ฟุตบอลพร้อมอ้างอิง ผลและโปรแกรมการแข่งขัน ตารางคะแนน และรายงานสรุปประจำสัปดาห์
พัฒนาต่อจากระบบ RAG (week4 / week5) และสถาปัตยกรรม API Backend ของ Travel Safety Assistant เดิมของทีม โดยเพิ่มข้อมูลจาก football-data.org และ API-Football

## เอกสาร — อ่านตามลำดับนี้

| ไฟล์ | เนื้อหา |
|---|---|
| [`docs/00_PLAN_OVERVIEW.md`](docs/00_PLAN_OVERVIEW.md) | แผนงาน สถาปัตยกรรม ตาราง service ขอบเขต |
| [`docs/CONTRACT.md`](docs/CONTRACT.md) | ข้อตกลง API ระหว่าง service |
| [`docs/GIT_FLOW.md`](docs/GIT_FLOW.md) | คู่มือใช้ git ของทีม — **อ่านก่อนเริ่มงาน** |
| [`docs/SCHEDULE.md`](docs/SCHEDULE.md) | ใครทำอะไร วันไหน |
| [`DL-06-Agentic-AI-System-I/`](DL-06-Agentic-AI-System-I/) | แผนต้นฉบับของอาจารย์ (8 โมดูล) |

## Branch

```
main      ← เวอร์ชันนำเสนอ · merge จาก develop เท่านั้น
develop   ← default branch · จุดรวมงาน · เข้าได้ผ่าน PR เท่านั้น
feature/<เลข>-<โมดูล>-<github-username>   ← branch ของแต่ละคน
```

## สถานะ

กำลังพัฒนา (อัปเดต 26 ก.ย. 2026)

| service | สถานะ |
|---|---|
| 02 API Backend · 05 Retrieval | อยู่ใน `develop` แล้ว |
| 01 Web (#4) · 03 Router (#15) · 06 Generation (#11) · 07 Football Data (#6) · Deploy (#16) | เปิด PR รอรีวิว |
| 04 AI Engines | ยังไม่เปิด PR (branch `feature/04-ai-model-selection-phonlakrit`) |

รันทั้งระบบด้วย `make up` (Docker Compose) ได้หลัง PR ของ Deploy และทุก service merge ครบ
