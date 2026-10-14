# บั๊ก: แชทตอบดาวซัลโวผิด (ตอบ Saka / Bruno Fernandes แทน Erling Haaland)

| หัวข้อ | รายละเอียด |
|---|---|
| วันที่พบ | 2026-09-30 |
| ผู้รายงาน | sakda1306 (หัวหน้าทีม) |
| ผู้รับผิดชอบแก้ | 08 Deploy & Monitoring (Peem-Atikorn) — ประสานงานกับเจ้าของโมดูลที่ต้องแก้ (ดู §7) |
| ความรุนแรง | **สูง** — แชทตอบข้อมูลผิดอย่างมั่นใจ พร้อมแหล่งอ้างอิง ผู้ใช้เชื่อได้ง่าย |
| โมดูลที่เกี่ยว | 03 AI Router (ต้นเหตุหลัก) · 05 Retrieval (ข้อจำกัด) · 06 Generation (ป้องกันซ้ำ) |
| สภาพแวดล้อม | stack เต็มผ่าน Docker Compose บน `develop` @ `688024a`, `PLAYER_INDEX_ENABLED=true`, ฤดูกาล 2026 นัดที่ 6 |

---

## 1. อาการ

**คำถาม:** `ใครทำประตูเยอะที่สุด`

**คำตอบที่ได้ (ผิด):**
> ผู้เล่นที่ทำประตูมากที่สุดในฤดูกาลพรีเมียร์ลีก 2026 (จนถึง 30 กันยายน 2026) มี 2 คนคือ Bukayo Saka ของ Arsenal FC ทำได้ 3 ลูก [4] และ Bruno Fernandes ของ Manchester United FC ทำได้ 3 ลูก [5]

**คำตอบที่ถูก:** Erling Haaland (Manchester City FC) 5 ประตู — รองลงมา Alexander Isak (Liverpool FC) 4 ประตู

ข้อมูลที่ถูกต้อง **มีอยู่ในระบบแล้ว** ทั้งสองที่:
- เอกสาร `standings-2026` หัวข้อ `Current top scorers / Golden Boot` เรียงอันดับไว้แล้ว: `1. Erling Haaland (Manchester City FC): 5 goals ...`
- เอกสาร `players-2026-team-65` (Man City) ส่วนของ Haaland มีบรรทัด `... season so far ...: 5 goals ...`

### อาการที่เกี่ยวข้อง (ต้นเหตุตระกูลเดียวกัน ให้แก้พร้อมกัน)

**คำถาม:** `ใครยิงเยอะที่สุดตอนนี้`
**คำตอบ:** `ไม่พบข้อมูลที่เพียงพอในคลังข้อมูลเพื่อตอบคำถามนี้` — ผิดเช่นกัน เพราะข้อมูลมีอยู่ (ดู §4.2)

---

## 2. วิธีทำซ้ำ

1. รัน stack ตาม `deploy/README.md` (`./deploy/tasks.ps1 up` แล้ว `./deploy/tasks.ps1 warmup`) โดยตั้ง `PLAYER_INDEX_ENABLED=true` ใน `.env`
   - ต้องมี PR #31 (ส่งตัวแปรนี้เข้าคอนเทนเนอร์ football-data) มิฉะนั้นเอกสารนักเตะจะไม่เข้า index
2. ตรวจว่า index มีข้อมูลครบ:
   ```powershell
   docker compose --env-file .env -f docker-compose.yml exec retrieval python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/index/stats').read().decode())"
   ```
   ที่ใช้ตอนพบบั๊ก: `{"standings":1, "player":20, "match_report":50, "fixtures":20, "trivia":1953}`
3. ล็อกอินหน้าเว็บ แล้วถามแชท `ใครทำประตูเยอะที่สุด` และ `ใครยิงเยอะที่สุดตอนนี้`

> หมายเหตุ: คำถามแรกถูกตัดสินที่ชั้น LLM ซึ่งผลอาจไม่เหมือนกันทุกครั้ง แต่ trace ที่บันทึกไว้ (§3) ยืนยันว่าเกิดขึ้นจริง

---

## 3. หลักฐาน

### 3.1 Trace ที่ระบบบันทึกไว้ (ตาราง `app.messages` ฐานข้อมูล `football`)

คำตอบที่ผิด (message id `01a0f1d6-c5fc-7000-9f59-aa12e740dd1b`):

```json
route: "football_rag", confidence: 0.92, reasoning: "llm: player_info"
trace: {
  "steps": [
    {"name": "engines.classify",   "ms": 9},
    {"name": "router.llm",         "ms": 805},
    {"name": "router.llm",         "ms": 815},
    {"name": "retrieval.search",   "ms": 35},
    {"name": "generation.grounded","ms": 1346}
  ],
  "intent": "player_info",
  "filters": {"season": "2026", "category": ["player"]},
  "rewritten_query": "Premier League top scorer most goals ใครทำประตูเยอะที่สุด",
  "decided_at_layer": "llm",
  "fallback": null
}
sources: [4] players-2026-team-57 (player), [5] players-2026-team-66 (player)
```

ดูซ้ำได้ด้วย:
```powershell
docker compose --env-file .env -f docker-compose.yml exec -T postgres psql -U app -d football -At -c "select route, reasoning, trace::text from app.messages where content like '%Bukayo Saka%' order by created_at desc limit 1"
```

### 3.2 เล่นการค้นซ้ำด้วยคำค้นและ filter เดียวกัน

`POST /search` ของ 05, `query = "Premier League top scorer most goals ใครทำประตูเยอะที่สุด"`, `top_k = 5`

| filter | ผลที่ได้ |
|---|---|
| `category: ["player"]`, `season: "2026"` | 5 chunk ของผู้เล่นที่ยิง **1, 1, 1, 3, 3** ประตู (Liverpool, Everton, Arsenal, Arsenal, Man United) — **ไม่มี Haaland** |
| `category: ["standings"]`, `season: "2026"` | `standings-2026` หัวข้อ Golden Boot: `1. Erling Haaland (Manchester City FC): 5 goals ... 2. Alexander Isak (Liverpool FC): 4 goals ...` |

สำหรับคำถาม `ใครยิงเยอะที่สุดตอนนี้` (กฎจัดเป็น trivia):

| filter | ผลที่ได้ |
|---|---|
| `category: ["trivia"]` | `trivia-0224` "Who scored the first Golden Goal...", `trivia-1878` "Which goalkeeper scored the most goals...", `trivia-0730` "Who scored the first goal in Copa America..." — ไม่เกี่ยวเลย |
| `category: ["standings"]` | `standings-2026` (มีคำตอบ) |

### 3.3 การตัดสินของชั้นกฎ (03) บนคอนเทนเนอร์ router

```python
decide("ใครทำประตูเยอะที่สุด", ...)      # -> None  (ไม่มีกฎจับ → ตกไป classifier → LLM)
decide("ใครยิงเยอะที่สุดตอนนี้", ...)     # -> ('football_rag', 'trivia_history', 'rules', {'category': ['trivia']}, ...)
```

---

## 4. ต้นเหตุ (ไล่ทีละชั้น)

### 4.1 Router ชั้น LLM จัด "ใครทำประตูเยอะที่สุด" เป็น `player_info` — **ต้นเหตุหลัก**

- ชั้นกฎไม่จับคำถามนี้: กฎ `standings_stats` (`services/03_ai_router_agent/app/decisions.py:88`) จับเฉพาะ `ตารางคะแนน, จ่าฝูง, อันดับ, กี่แต้ม, ดาวซัลโว, standings, points, scorer, golden boot` — ไม่มี "ทำประตูเยอะที่สุด"
- classifier ของ 04 ใช้จริงเฉพาะ `score ≥ 0.75` (`decisions.py:45`) ซึ่งเกิดกับคำถามราว 1% → ตกไป LLM (`router.py:65`)
- prompt ของ LLM (`services/03_ai_router_agent/app/clients.py:70-76`) **ระบุแค่ชื่อ intent** 9 ตัว ไม่มีคำอธิบายขอบเขต เมื่อ `player_info` ถูกเพิ่มใน PR #28 LLM จึงเลือก `player_info` สำหรับคำถาม "ผู้เล่นคนไหนยิงเยอะที่สุด" ทั้งที่ตาม **CONTRACT §3 (v1.5)** คำถามดาวซัลโวเป็น `standings_stats` (`["standings"]`)

### 4.2 Router ชั้นกฎจัด "ใครยิงเยอะที่สุดตอนนี้" เป็น `trivia_history`

- กฎ trivia ตัวสุดท้าย (`decisions.py:95`) มีคำว่า **`ใครยิง`** จึงจับทุกคำถามที่ขึ้นต้นด้วย "ใครยิง" รวมถึงคำถามดาวซัลโวฤดูกาลปัจจุบัน
- กฎ `standings_stats` (บรรทัด 88) มาก่อนก็จริง แต่ไม่มีคำที่ตรงกับ "ยิงเยอะที่สุด"
- กฎนี้มีมาก่อนงานข้อมูลนักเตะ ไม่ได้เกิดจาก PR ล่าสุด

### 4.3 Retrieval (05) หาอันดับไม่ได้ — **ข้อจำกัดโดยธรรมชาติ ไม่ใช่บั๊กของ 05**

เอกสาร `player` ตัด chunk ตามหัวข้อ `##` = 1 chunk ต่อผู้เล่น (ตาม CONTRACT §6) การค้นแบบ BM25 + vector คืน chunk ที่ "ข้อความคล้ายคำค้น" ที่สุด ไม่ได้คืน "คนที่ยิงเยอะที่สุด" คำถามแบบจัดอันดับจึงต้องไปที่เอกสาร `standings-<season>` ซึ่งเรียงอันดับไว้แล้วเท่านั้น

### 4.4 Generation (06) สรุปเกินข้อมูล — **ปัจจัยเสริม**

06 ได้ context 5 chunk แล้วตอบว่า "ทำประตูมากที่สุดในฤดูกาล" จาก 5 คนนั้น ทั้งที่ context ไม่ใช่รายชื่อครบ prompt grounded (`services/06_llm_generation/prompts/grounded.j2`) มีกติกาให้คัดลอกตัวเลขจาก references ตรง ๆ (ข้อ 2, บรรทัด 9) และให้บอกเมื่อตอบได้แค่บางส่วน (บรรทัด 16) — LLM ทำตามข้อแรก (เลข 3 ถูกต้องตาม chunk) แต่ไม่ทำตามข้อหลัง เพราะไม่มีกติกาที่พูดถึงการสรุป "มากที่สุด/อันดับ 1" โดยตรง

### 4.5 ทำไมเพิ่งเห็น

ก่อน PR #29 เอกสารนักเตะไม่มีจำนวนประตู ถ้าถูกส่งไปหมวด `player` แชทจะตอบ "ไม่พบข้อมูล" หลัง #29 มีบรรทัด `... goals ...` ทำให้ 06 มีตัวเลขไปสรุป ความผิดพลาดของ router จึงกลายเป็นคำตอบผิดที่ดูน่าเชื่อ

---

## 5. วิธีแก้ที่เสนอ

### A. Router (03) — **ต้องทำ**

**A1. กฎชั้น rules (`decisions.py`, ฟังก์ชัน `_intent`)** — เพิ่มก่อนกฎ trivia (บรรทัด ~84) และก่อน/รวมกับกฎ `standings_stats` (บรรทัด 88):

- ถ้าข้อความมี (`ยิง` หรือ `ทำประตู` หรือ `ประตู`) **และ** (`มากที่สุด` หรือ `เยอะที่สุด` หรือ `เยอะสุด` หรือ `สูงสุด`) **และไม่มี** (`ตลอดกาล`, `ประวัติศาสตร์`, `all-time`, `all time`, `ever`) → `standings_stats`
- อังกฤษ: `top scorer`, `most goals`, `leading scorer` (มี `scorer` อยู่แล้ว) → `standings_stats` เว้นแต่มี `all-time`/`ever`/`in history`
- ตรวจ rewrite ที่ `decisions.py:116` — ตอนนี้ใช้ topic `top scorer` เฉพาะเมื่อมีคำว่า "ดาวซัลโว" ควรให้คำถามที่เข้ากฎใหม่ได้ topic `top scorer` ด้วย

**A2. prompt ชั้น LLM (`clients.py:70-76`)** — อธิบายขอบเขต intent อย่างน้อย:
- `standings_stats`: ตารางคะแนน อันดับทีม **ดาวซัลโว / ใครยิงหรือทำประตูมากที่สุดในฤดูกาลนี้ / คำถามจัดอันดับผู้เล่น**
- `player_info`: สควอด รายชื่อ โปรไฟล์ ตำแหน่ง อายุ สัญชาติ โค้ช **หรือสถิติของผู้เล่นที่ระบุชื่อ** — ไม่ใช้กับคำถามจัดอันดับ
- `trivia_history`: สถิติ/เหตุการณ์ในอดีตหรือตลอดกาล

**เกณฑ์ยอมรับ (ต้องมี test ใน `services/03_ai_router_agent/tests/test_decisions.py` ที่ล้มก่อนแก้):**

| คำถาม | intent ที่ต้องได้ | category |
|---|---|---|
| ใครทำประตูเยอะที่สุด | `standings_stats` (ชั้น rules) | `["standings"]` |
| ใครยิงเยอะที่สุดตอนนี้ | `standings_stats` | `["standings"]` |
| นักเตะคนไหนยิงประตูมากที่สุดฤดูกาลนี้ | `standings_stats` | `["standings"]` |
| Who has the most goals this season | `standings_stats` | `["standings"]` |
| ใครยิงประตูมากที่สุดตลอดกาลของพรีเมียร์ลีก | `trivia_history` (คงเดิม) | `["trivia"]` |
| ใครยิงประตูชัยให้ลิเวอร์พูลในนัดชิงปี 2005 | `trivia_history` (คงเดิม) | `["trivia"]` |
| ซาก้ายิงไปกี่ลูกแล้ว / ซาก้าเล่นตำแหน่งอะไร | ไม่ถูกดึงไป `standings_stats` โดยกฎใหม่ | — |

- test เดิม `PlayerInfoTests.test_neighbouring_questions_keep_their_intent` มีเคส `("นักเตะคนไหนยิงประตูมากที่สุดฤดูกาลนี้", None)` — **ต้องเปลี่ยนเป็น `standings_stats`** (พฤติกรรมใหม่ถูกกว่า)
- `tests/routing_cases.jsonl` 41 เคสเดิมต้องผ่านทั้งหมด (`test_routing_cases`)
- test ของ prompt: ยืนยันว่า system prompt มีคำอธิบายของ `standings_stats` ที่พูดถึงดาวซัลโว/การจัดอันดับ (แบบเดียวกับ `LlmPromptTests` ใน `tests/test_clients.py`)

### B. Generation (06) — **ควรทำ (ป้องกันซ้ำ)**

ใน `prompts/grounded.j2` เพิ่มกติกา: ห้ามสรุปว่าใคร "มากที่สุด / อันดับหนึ่ง / เยอะที่สุด" เว้นแต่ context มีรายการที่ระบุการจัดอันดับไว้ชัดเจน (เช่นหัวข้อ `Golden Boot` / `top scorers`) ถ้าไม่มี ให้ตอบเฉพาะข้อมูลที่เห็น พร้อมบอกว่าเป็นข้อมูลบางส่วน

- test: ส่ง context เป็น chunk ของผู้เล่นทีละคน (ไม่มีรายการจัดอันดับ) แล้วถาม "ใครทำประตูเยอะที่สุด" → คำตอบต้องไม่อ้างว่าเป็นอันดับหนึ่ง (ทดสอบกับ LLM mock/fixture ตามรูปแบบเดิมของ 06)
- ข้อนี้ **ไม่แทน** A — ถ้า router ส่งไปหมวดถูก คำตอบจะถูกตั้งแต่ต้น

### ไม่ต้องแก้

- 05: การค้นทำงานตามออกแบบ
- 07: ข้อมูล `standings-2026` และ `players-*` ถูกต้อง

---

## 6. วิธีตรวจว่าแก้สำเร็จ (บน stack จริง)

1. build ใหม่: `./deploy/tasks.ps1 up` (router และ generation ต้อง build ใหม่)
2. ถามแชท 4 คำถามแรกในตาราง §5-A แล้วเปิด "ดูขั้นตอนการตอบ" ต้องเห็น `intent: standings_stats`, category `standings` และคำตอบระบุ **Erling Haaland 5 ประตู**
3. ถาม "ใครยิงประตูมากที่สุดตลอดกาลของพรีเมียร์ลีก" ต้องยังเป็นคำตอบจากคลัง trivia
4. ตรวจ trace ใน DB ด้วยคำสั่ง §3.1 (เปลี่ยน `like` เป็นข้อความคำตอบใหม่)
5. ผลทดสอบของโมดูลที่แก้ต้องผ่านทั้งชุด (`python -m pytest -q` ในโฟลเดอร์ของ 03 และ 06)

---

## 7. ความเป็นเจ้าของและขั้นตอน (ตาม `docs/GIT_FLOW.md`)

- โค้ดที่ต้องแก้อยู่ใน **03** (`@mahawongsupawit125-coder`) และ **06** (`@cira1234`) — 08 ไม่ใช่เจ้าของโฟลเดอร์ ต้องแจ้งเจ้าของก่อน และ PR ต้องได้ approve จากเจ้าของโมดูลตาม CODEOWNERS
- แยก PR ต่อโมดูล (03 หนึ่ง PR, 06 หนึ่ง PR) base `develop`
- ไม่ต้องแก้ `docs/CONTRACT.md` — ตาราง intent ของสัญญา v1.5 ระบุไว้แล้วว่าดาวซัลโวเป็น `standings_stats` งานนี้คือทำให้โค้ดตรงกับสัญญา

---

## 8. สิ่งที่พบระหว่างตรวจ (แยกเรื่อง ไม่ต้องแก้ใน PR นี้)

- log ของ router มี `{"event": "team_cache_fallback"}` ซ้ำหลายครั้ง แปลว่า router ดึงรายชื่อทีมจาก 07 ไม่สำเร็จแล้วใช้ไฟล์ `data/team_aliases.json` แทน ยังไม่กระทบคำตอบ แต่ควรตรวจสาเหตุภายหลัง
- ข้อจำกัดของข้อมูล: แผนฟรีของ football-data.org ไม่รายงานแอสซิสต์ของผู้เล่นส่วนใหญ่ คำตอบเรื่องแอสซิสต์จะเป็น "ไม่มีข้อมูล" ซึ่งเป็นพฤติกรรมที่ตั้งใจ ไม่ใช่บั๊ก
