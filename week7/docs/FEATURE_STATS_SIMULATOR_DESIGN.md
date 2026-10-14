# FEATURE_STATS_SIMULATOR_DESIGN.md — ถามสถิติย้อนหลัง + จำลองฤดูกาล · ผู้ช่วยฟุตบอล

> สถานะ: **ร่างรอรีวิว** (27 ก.ย. 2026) · อ่านคู่กับ `CONTRACT.md` (v1.5) และ `services/07_football_data/HISTORICAL_DATA.md`
> เอกสารนี้เสนอฟีเจอร์เพิ่ม 2 ตัว และการแก้ CONTRACT เป็น **v1.6** · ยังไม่มีผลจนกว่าทีมตกลงและ merge

## 0. สรุปสั้น

| | ฟีเจอร์ 1 · ถามสถิติย้อนหลัง | ฟีเจอร์ 2 · จำลองฤดูกาล |
|---|---|---|
| ผู้ใช้ถาม | "แมนยูเจอลิเวอร์พูลในบ้านชนะกี่ครั้งตั้งแต่ปี 2010" | "อาร์เซนอลมีโอกาสแชมป์กี่ %" · หน้าเว็บ what-if |
| วิธีตอบ | router ใช้ LLM **เลือก tool** → 07 คำนวณจากตารางย้อนหลัง → 06 เรียบเรียง | 07 เตรียมข้อมูล → 04 จำลอง Monte Carlo ด้วย Poisson → 06 เรียบเรียง / หน้าเว็บแสดง |
| ตัวเลขมาจาก | โค้ดที่คำนวณจาก `historical_matches` / `historical_standings` (1992/93–2025/26) | แบบจำลองที่วัดผลย้อนหลังได้ (backtest) |
| intent | ใหม่ `history_stats` → route ใหม่ `stats_tool` | เดิม `prediction` → `local_ai` (เปลี่ยนวิธีทำงานภายใน) |

หลักร่วมของทั้งสองฟีเจอร์: **LLM ไม่เป็นคนคิดตัวเลข** LLM มีหน้าที่แค่เลือก tool + ดึงพารามิเตอร์ (03) และเรียบเรียงภาษา (06) ส่วนตัวเลขมาจากโค้ดที่เทสได้

## 1. เป้าหมาย / ไม่ใช่เป้าหมาย

**เป้าหมาย**
- ตอบคำถามที่ต้องนับ / รวม / เปรียบเทียบข้อมูลย้อนหลังหลายนัดได้ถูกต้อง ซึ่ง RAG เดิมทำไม่ได้
- ให้ router เป็น agent ที่เลือก tool เองจริง และแสดงการตัดสินใจใน `trace`
- ให้ `/local/predict` (ตอนนี้ตอบ 501) ใช้งานได้จริง และเพิ่มการจำลองทั้งฤดูกาล
- มีตัวเลขประเมินผลของทั้งสองฟีเจอร์ใน `eval/`

**ไม่ใช่เป้าหมาย**
- text-to-SQL หรือให้ LLM query ฐานข้อมูลเอง
- สถิติระดับนักเตะ (ประตู / ใบเหลือง / เตะมุม) ย้อนหลัง — ข้อมูลไม่ครบทุกฤดูกาล (ดู `HISTORICAL_DATA.md`)
- กติกาจัดอันดับด้วย head-to-head ของ PL ในการจำลอง
- ราคาต่อรอง / ทีเด็ด ในรูปแบบใดก็ตาม

## 2. เงื่อนไขก่อนเริ่ม

1. PR #22 (07), #21 (04), #15 (03) merge เข้า `develop` แล้ว · งานนี้เปิด branch ใหม่จาก `develop` หลังจากนั้น ไม่ merge branch ของเพื่อนเข้ามาก่อน
2. ทีมตกลงเรื่อง `category: historical` และ `origin: openfootball | fjelstul` ตามที่ PR #22 เสนอ (ข้อนี้ถูกรวมไว้ใน v1.6 ของเอกสารนี้)
3. CONTRACT ต้องขึ้น v1.5 → **v1.6** ตาม §8 ของเอกสารนี้ **ก่อน** merge โค้ดชิ้นแรก

## 3. ฟีเจอร์ 1 · ถามสถิติย้อนหลัง (Stats Tool Agent)

### 3.1 เส้นทาง

```
ผู้ใช้ → 02 api → 03 router
  ① guard / rules / classifier / LLM → intent = history_stats
  ② router.tool_select: เรียก LLM 1 ครั้ง (tools = 6 schema, tool_choice = "required")
  ③ router ตรวจพารามิเตอร์ (ชื่อทีม ↔ /football/history/clubs, ช่วงฤดูกาล)
  ④ GET 07 /football/history/<tool>?...  → StatsResult
  ⑤ 06 /generate mode=grounded · contexts = [{ref: 1, text: StatsResult.summary, source: StatsResult.source}]
← RouteResponse (route = stats_tool, engines_used = ["football-data", "generation"])
```

`trace.steps` ต้องมีอย่างน้อย `router.tool_select`, `football.history`, `generation.grounded` และ `trace` เพิ่ม field optional `tool: {name, params}` ให้หน้าเว็บแสดงว่า agent เลือก tool อะไร

### 3.2 Tool

ทุก tool เป็น `GET` อ่านอย่างเดียวที่ 07 · ใช้ข้อมูลฤดูกาล `1992`–`2025` (1992/93–2025/26) เท่านั้น · `season` ใช้รูปแบบเดียวกับทั้งระบบ คือปีที่ฤดูกาลเริ่ม (`"2015"` = 2015/16)

| tool | path | พารามิเตอร์ | ตัวอย่างคำถาม |
|---|---|---|---|
| `head_to_head` | `/football/history/head-to-head` | `team_a, team_b` (slug) · `venue ∈ any \| team_a_home \| team_b_home` (ค่าเริ่ม `any`) · `season_from?, season_to?` | แมนยูเจอลิเวอร์พูลชนะกี่ครั้ง |
| `team_season` | `/football/history/team-season` | `team, season` | อาร์เซนอลปี 2003/04 ได้กี่แต้ม |
| `season_table` | `/football/history/season-table` | `season` · `position_from?, position_to?` (1–20/22) | ใครตกชั้นปี 2020/21 |
| `season_summary` | `/football/history/season-summary` | `season_from?, season_to?` | ใครแชมป์บ้างตั้งแต่ปี 2010 |
| `team_records` | `/football/history/team-records` | `team?` · `metric ∈ points \| goals_for \| goals_against \| goal_difference \| wins \| losses` · `order ∈ max \| min` · `season_from?, season_to?` · `limit ≤ 10` (ค่าเริ่ม 3) | ฤดูกาลที่เชลซีเสียประตูน้อยสุด |
| `biggest_wins` | `/football/history/biggest-wins` | `team?, season?` · `limit ≤ 10` (ค่าเริ่ม 5) | แมนยูชนะขาดสุดคือนัดไหน |

และ `GET /football/history/clubs` → `{clubs: [{slug, name, team_id, aliases, seasons: ["1992", ...]}]}` · `aliases` รวมชื่อเล่นไทยจาก `team_aliases.json` (ทีมปัจจุบัน) และเพิ่มชื่อไทยของสโมสรที่เคยอยู่ PL แต่ไม่อยู่ฤดูกาลปัจจุบัน

**หมายเหตุการคำนวณ**
- `team_records` เมื่อฤดูกาลมีจำนวนนัดต่างกัน (42 นัดช่วง 1992–1994, 38 นัดหลังจากนั้น) ให้คืนทั้งค่ารวมและค่าต่อนัด (`per_match`) และใน `summary` ระบุจำนวนนัดของฤดูกาลนั้น
- แต้มใน `team_season` / `season_table` ใช้แต้มหลังหักตาม `point_deductions.json`
- `season_table` และ `season_summary` ต้องตรงกับตาราง Fjelstul ที่ตรวจไว้ใน PR #22

### 3.3 Response ร่วม (`StatsResult`)

```jsonc
{
  "tool": "head_to_head",
  "params": { "team_a": "manchester-united", "team_b": "liverpool", "venue": "team_a_home", "season_from": "2010", "season_to": "2025" },
  "result": { "matches": 16, "team_a_wins": 7, "draws": 4, "team_b_wins": 5, "team_a_goals": 22, "team_b_goals": 19,
              "last_matches": [ { "season": "2025", "date": "2026-01-18", "home": "...", "away": "...", "score": "1-2" } ] },
  "summary": "Manchester United vs Liverpool at Old Trafford, 2010/11–2025/26: 16 matches — Manchester United 7 wins, 4 draws, Liverpool 5 wins; goals 22–19.",
  "coverage": { "season_from": "2010", "season_to": "2025", "matches_used": 16 },
  "source": {
    "ref": 1, "doc_id": "stats-head_to_head-3f9a1c2e", "title": "สถิติเจอกัน Manchester United vs Liverpool (2010/11–2025/26)",
    "category": "historical", "origin": "fjelstul", "season": null, "matchweek": null,
    "team_ids": [66, 64], "fetched_at": null,
    "url": "https://github.com/jfjelstul/englishfootball"
  }
}
```

- `summary` สร้างจาก template ในโค้ด **ไม่ผ่าน LLM** · ภาษาอังกฤษ (06 แปลตอนเรียบเรียง)
- `doc_id` = `stats-<tool>-<8 ตัวแรกของ sha1 ของ params ที่เรียงคีย์แล้ว>` · ไม่ถูก index เข้า 05
- `origin` = `fjelstul` เมื่อคำนวณจากตารางจบฤดูกาล · `openfootball` เมื่อคำนวณจากผลรายนัด
- หน้าเว็บต้องแสดงเครดิตข้อมูล CC-BY-SA 4.0 เมื่อ `category = historical` (ข้อความตาม `HISTORICAL_DATA.md` "Credits and license")

### 3.4 การเลือก tool (03)

- เรียก LLM ผ่านไลบรารี `openai` ตาม CONTRACT §8 (Groq → Gemini) ด้วย `tools` = 6 schema ข้างบน และ `tool_choice = "required"` · system prompt บอกปีปัจจุบันจาก `context.season` และกติกาแปลงปี: "ปี 2015" / "ฤดูกาล 2015/16" → `"2015"`
- ชื่อทีมที่ LLM ส่งมา ให้ router จับคู่กับ `/football/history/clubs` เอง (cache 1 ชม.) · จับคู่ได้ 1 ทีม → ใช้ slug · หลายทีม → `clarify` · ไม่เจอ → `clarify`
- ตรวจ `season_*` อยู่ในช่วง `1992`–`2025` และ `season_from ≤ season_to` · enum ต้องอยู่ในค่าที่กำหนด · ไม่ผ่าน → ไม่เรียก 07
- LLM ไม่เลือก tool / ส่ง arguments ที่ parse ไม่ได้ → ทางถอย 3.5 ข้อ "เล่าเรื่อง"

### 3.5 กรณีผิดปกติ (router ตอบ 200 เสมอตาม CONTRACT §2)

| สถานการณ์ | route | คำตอบ | `trace.fallback` |
|---|---|---|---|
| ชื่อทีมไม่เจอ / กำกวม | `clarify` | ถามกลับ เช่น "หมายถึงแมนยูหรือแมนซิตี้ครับ" | – |
| ฤดูกาลอยู่นอก 1992–2025 | `stats_tool` | "มีข้อมูลย้อนหลังช่วง 1992/93–2025/26" · ถ้าถามฤดูกาลปัจจุบัน → ส่งต่อเส้น `standings_stats` เดิม | `history_out_of_range` |
| เลือก tool ไม่ได้ / คำถามเชิงเล่าเรื่อง | `football_rag` | ค้น 05 ด้วย `category: ["historical"]` แล้ว `grounded` | `stats_no_tool` |
| 07 ล่ม / timeout (8 วินาที) | `stats_tool` | "ตอนนี้ดึงสถิติย้อนหลังไม่ได้ ลองใหม่อีกครั้ง" · **ห้ามถอยไป `general_ai`** | `history_down` |
| LLM ล่มทั้งสองเจ้าที่ขั้นเลือก tool | `football_rag` | เหมือนแถว "เลือก tool ไม่ได้" | `stats_no_tool` |

07 ตอบ `422 VALIDATION_ERROR` เมื่อพารามิเตอร์ผิด และ `404 NOT_FOUND` เมื่อไม่มีข้อมูล (เช่นสองทีมไม่เคยเจอกัน → router ตอบว่า "ไม่เคยพบกันในพรีเมียร์ลีกช่วงนี้" ไม่ใช่ error)

## 4. ฟีเจอร์ 2 · จำลองฤดูกาล (Season Simulator)

### 4.1 ทิศทางการเรียก

```
หน้าเว็บ → 02 /api/football/simulation[/what-if] → 07 ─(inputs)→ 04 /local/simulate
แชท   → 03 (intent prediction → tool) → 07 /football/simulation | /football/predict ─→ 04
```

เรียกทางเดียว **07 → 04** · 04 ไม่มี state และไม่เรียก service อื่น

### 4.2 04 · `POST /local/simulate` (ใหม่)

```jsonc
// SimulateRequest
{
  "request_id": "uuid",
  "inputs": {
    "season": "2026", "as_of": "2026-09-22T09:30:00+07:00",
    "table":     [ { "team_id": 57, "points": 12, "goal_difference": 6, "goals_for": 11, "played": 5 } ],   // 20 ทีม
    "remaining": [ { "match_id": "uuid", "home_team_id": 57, "away_team_id": 61 } ],
    "strengths": { "57": { "attack": 1.90, "defense": 0.80, "matches_used": 43 } },
    "league_avg_goals": 1.38,
    "home_advantage": 1.15,
    "relegation_places": 3
  },
  "fixed_results": [ { "match_id": "uuid", "home_goals": 2, "away_goals": 1 } ],   // optional ≤ 10 · ต้องอยู่ใน remaining
  "n_sims": 10000,       // 1,000–20,000 · ค่าเริ่ม 10,000
  "seed": 42             // optional · ใส่แล้วผลต้องซ้ำได้
}
```

ตอบ `EngineResult` (CONTRACT §3) · `engine: "local_ai"` · `model: "poisson-mc-v1"` · `token_usage: {input: 0, output: 0}`

```jsonc
"data": {
  "season": "2026", "as_of": "...", "n_sims": 10000, "remaining_matches": 330, "fixed_results": 0,
  "teams": [ { "team_id": 57, "points": 12, "expected_points": 74.3,
               "p_title": 0.31, "p_top4": 0.82, "p_relegation": 0.0,
               "position_probs": [0.31, 0.24, ...] } ]   // 20 ค่า รวม = 1 · เรียง teams ตาม expected_points มาก → น้อย
}
```

**วิธีคำนวณ**
- expected goals ของแต่ละนัดใช้ `expected_goals()` เดิมใน `app/poisson.py` (attack × defense ของอีกฝั่ง × ค่าเฉลี่ยลีก × home advantage)
- สุ่มประตูแบบ vectorized ด้วย numpy `Generator.poisson` ขนาด `[n_sims, len(remaining)]` ครั้งเดียว · นัดใน `fixed_results` ใช้สกอร์ที่กำหนดทุกรอบ
- จัดอันดับ: แต้ม → ผลต่างประตู → ประตูได้ → สุ่ม (ใช้ seed เดียวกัน)
- `content` = สรุปภาษาไทยสั้น ๆ เช่น "จำลอง 10,000 ครั้ง: Arsenal แชมป์ 31%, ..."
- `remaining` ว่าง (ฤดูกาลจบแล้ว) → คืนตารางปัจจุบันด้วยความน่าจะเป็น 0/1 ไม่ error

**`/local/predict` (ทำให้ใช้งานได้จริง)** · เพิ่ม field optional `home_strength`, `away_strength` (รูปเดียวกับ `strengths[*]`) และ `league_avg_goals` · ถ้าไม่ส่งมา ยังตอบ 501 `NOT_IMPLEMENTED` เหมือนเดิม (ไม่ทำให้คนเรียกรุ่นเก่าพัง) · `data` ตาม CONTRACT §3 เดิม + `home_xg`, `away_xg`, `most_likely_score` · `method: "poisson-v1"`

### 4.3 07 · เตรียมข้อมูลและเก็บผล

**ความแข็งของทีม** (ต่อทีม คำนวณแยก attack / defense)

```
attack  = (ประตูได้ฤดูกาลนี้ + k × ค่าเฉลี่ยประตูได้ต่อนัดฤดูกาลก่อน) / (นัดฤดูกาลนี้ + k)
defense = (ประตูเสียฤดูกาลนี้ + k × ค่าเฉลี่ยประตูเสียต่อนัดฤดูกาลก่อน) / (นัดฤดูกาลนี้ + k)
k = 10
```

- ฤดูกาลก่อนมาจาก `historical_matches` (ฤดูกาล `season - 1`)
- ทีมที่ไม่ได้อยู่ PL ฤดูกาลก่อน (เลื่อนชั้น) ใช้ค่าเฉลี่ยของ 3 ทีมที่ตกชั้นฤดูกาลก่อนแทน
- `league_avg_goals` = ค่าเฉลี่ยประตูต่อทีมต่อนัดของฤดูกาลก่อน ผสมกับฤดูกาลนี้ด้วยสูตรเดียวกัน
- `matches_used` = นัดฤดูกาลนี้ + นัดฤดูกาลก่อน
- `remaining` = นัดฤดูกาลปัจจุบันที่ `status` ยังไม่จบ (รวมนัดเลื่อน)
- `table` มาจากตารางคะแนนสดล่าสุด (แต้มรวมการหักแต้มแล้ว)

**Endpoint ใหม่**

| Method | Path | ทำอะไร | Response 200 |
|---|---|---|---|
| GET | `/football/simulation` | ผลจำลองของฤดูกาลปัจจุบัน · query `season?` | `SimulationSnapshot` |
| POST | `/football/simulation/what-if` | body `{fixed_results: [≤10], request_id}` · เรียก 04 สดด้วย `n_sims = 5000` · ไม่เก็บผล | `SimulationSnapshot` (`baseline: false`) |
| GET | `/football/predict` | query `home_team_id, away_team_id` · เรียก `/local/predict` พร้อม strengths | `EngineResult` ของ 04 ส่งต่อทั้งก้อน |

```jsonc
// SimulationSnapshot
{ "season": "2026", "as_of": "...", "computed_at": "...", "baseline": true, "stale": false,
  "n_sims": 10000, "model": "poisson-mc-v1", "teams": [ ...เหมือน data.teams ของ 04 + name, short_name... ] }
```

**การเก็บผล** · ตารางใหม่ `simulation_snapshots` (`season`, `inputs_hash`, `payload`, `computed_at`) · `inputs_hash` = sha1 ของ `inputs` · หลัง ingest สำเร็จ 07 คำนวณใหม่ใน background (seed = 42 เพื่อผลซ้ำได้) · `GET /football/simulation` ถ้า hash ล่าสุดยังไม่มีผล → เรียก 04 แล้วเก็บ

**เมื่อ 04 ล่ม** · คืน snapshot ล่าสุดที่มีพร้อม `stale: true` · ไม่เคยมีเลย → `503 SIMULATION_UNAVAILABLE` · what-if เมื่อ 04 ล่ม → 503 เสมอ

### 4.4 03 · router (intent `prediction` เดิม)

ตาราง intent ไม่เปลี่ยน · เส้น `local_ai` ของ intent `prediction` เปลี่ยนเป็นขั้นเลือก tool แบบเดียวกับ 3.4 โดยมี 2 tool

| tool | เรียก | ตัวอย่าง |
|---|---|---|
| `match_prediction(home, away)` | 07 `GET /football/predict` | ลิเวอร์พูลกับซิตี้ใครน่าจะชนะ |
| `season_simulation(team?, focus ∈ title \| top4 \| relegation \| all)` | 07 `GET /football/simulation` | อาร์เซนอลมีโอกาสแชมป์กี่ % · ใครเสี่ยงตกชั้น |

- ผลส่งต่อ 06 `grounded` · context เป็นข้อความสรุปจากโค้ด (ไม่ผ่าน LLM) · `source.category = "simulation"`, `origin = "generated"`, `doc_id = "sim-<season>-<inputs_hash 8 ตัว>"` หรือ `"pred-<season>-<home>-<away>"`
- 06 ต่อท้ายคำตอบทุกครั้ง: "ประมาณการจากแบบจำลองทางสถิติ เพื่อความบันเทิง ไม่ใช่คำแนะนำการพนัน" · ด่าน safety เรื่องพนันใน 06 ยังทำงานตามเดิม
- 07 / 04 ล่ม → "ฟีเจอร์ทำนายผลยังไม่พร้อมใช้งานตอนนี้" · `trace.fallback = "simulation_down"` · ห้ามถอยไป `general_ai`

### 4.5 02 · api

| Method | Path | ส่งต่อไป | หมายเหตุ |
|---|---|---|---|
| GET | `/api/football/simulation` | 07 `GET /football/simulation` | cache 5 นาที |
| POST | `/api/football/simulation/what-if` | 07 `POST /football/simulation/what-if` | ต้อง login · rate limit 10 ครั้ง / นาที / ผู้ใช้ · ตรวจ `fixed_results ≤ 10` และสกอร์ 0–15 |

### 4.6 01 · หน้า `/football/simulation`

- ตาราง 20 ทีม: แต้มตอนนี้ · แต้มที่คาด · แถบ % แชมป์ / Top 4 / ตกชั้น · กดทีมเพื่อดูกราฟการกระจายอันดับ 1–20
- แผง what-if: เลือกนัดที่ยังไม่แข่งได้ไม่เกิน 10 นัด · ตั้งผลเป็นชนะ / เสมอ / แพ้ (แปลงเป็น 1–0 / 1–1 / 0–1) หรือกรอกสกอร์ · กด "จำลองใหม่" · แสดงผลต่างเทียบ baseline (เช่น +12%) · ปุ่มล้างค่า
- badge "ข้อมูล ณ `as_of`" และป้าย "ผลเก่า" เมื่อ `stale`
- ข้อความเตือนเรื่องพนันใต้ตาราง

## 5. ประเมินผล (`eval/`)

| ชุด | วิธี | ตัวชี้วัด | ไฟล์ผล |
|---|---|---|---|
| stats routing | 30 คำถามสถิติ (ไทย 20 / อังกฤษ 10) พร้อม tool + params + ตัวเลขที่คำนวณไว้ล่วงหน้า · เพิ่มคำถามที่ไม่ควรเข้า `stats_tool` 10 ข้อ | tool accuracy · params exact match · % คำตอบที่มีตัวเลขตรง | `eval/results/stats_tool.json` |
| stats correctness | เทสใน 07 เทียบ `season_table` / `season_summary` กับตาราง Fjelstul ทุกฤดูกาล และ `head_to_head` ของ 5 คู่กับค่าที่นับมือไว้ | ผ่าน / ไม่ผ่าน | pytest |
| season backtest | ตัดข้อมูลที่แมตช์วีค 19 ของฤดูกาล 2010–2025 จำลองต่อ 10,000 ครั้ง | Brier score ของ แชมป์ / Top 4 / ตกชั้น เทียบ baseline "ตารางครึ่งฤดูกาลคงเดิม" | `eval/results/simulation.json` |
| match backtest | ทายทุกนัดของฤดูกาล 2015–2025 ด้วยข้อมูลก่อนนัดนั้น | Brier score + log loss ของ H/D/A เทียบ baseline อัตราเจ้าบ้านชนะ / เสมอ / แพ้ของลีก | `eval/results/simulation.json` |

## 6. การเทส

- **07**: pure function ของแต่ละ tool เทสด้วยข้อมูลเล็กที่สร้างเอง + เทสกับข้อมูลจริงเมื่อมี input (skip เมื่อไม่มี เหมือนเทสเดิมของ PR #22) · เทสการคำนวณ strengths (ทีมเลื่อนชั้น, ต้นฤดูกาลที่ยังไม่มีนัด) · เทส endpoint: 422 / 404 / stale / 503
- **04**: seed เดียวกันได้ผลเดียวกัน · `position_probs` ของทุกทีมรวม = 1 และทุกอันดับรวม = 1 · ทีมที่แข็งกว่าชัดเจนได้ `p_title` สูงกว่า · `fixed_results` ถูกใช้จริง · `remaining` ว่าง · 10,000 ครั้งกับ 380 นัดเสร็จ < 2 วินาทีบน CI
- **03**: mock LLM คืน tool call แต่ละแบบ → เรียก 07 ถูก path/params · ชื่อทีมกำกวม → clarify · 07 ล่ม → ไม่เรียก `general_ai` · เพิ่มเคสใน `routing_cases.jsonl`
- **02**: proxy + rate limit + ตรวจ body
- **01**: หน้า simulation แสดงได้ทั้งกรณีปกติ / stale / 503 · what-if ส่ง body ถูก

## 7. แบ่งงาน

| service | เจ้าของ (ตาม SCHEDULE) | งาน |
|---|---|---|
| 07 | member5 | `app/history_stats.py` (6 tool + clubs) · `app/strengths.py` · `app/simulation.py` (สร้าง inputs, เรียก 04, snapshot) · endpoint §3.2 / §4.3 · ตาราง `simulation_snapshots` · ชื่อไทยของสโมสรย้อนหลัง |
| 04 | member3 | `app/simulate.py` (numpy) · `POST /local/simulate` · `/local/predict` ใช้งานจริง · เพิ่ม intent `history_stats` ใน `data/intents.csv` (ประโยคใหม่ ไม่ซ้ำชุดทดสอบ) แล้ว train ใหม่ |
| 03 | member2 | `app/tools.py` (schema + ตรวจพารามิเตอร์ + เรียก 07) · route `stats_tool` · tool ใต้ `prediction` · ทางถอย §3.5 / §4.4 · trace |
| 05 | sakda1306 | validator รับ `category: historical` + `origin` ใหม่ · เปิด historical documents ใน index (ทางถอย "เล่าเรื่อง") |
| 06 | member4 | รับ `category` ใหม่ใน Source · ข้อความต่อท้ายของ simulation |
| 02 | sakda1306 | proxy §4.5 + rate limit |
| 01 | member1 | ป้าย route `stats_tool` · เครดิต CC-BY-SA · แสดง `trace.tool` · หน้า `/football/simulation` |
| eval | member6 | ชุดคำถาม stats · สคริปต์ backtest · ใส่ผลใน `eval/report.html` |

ลำดับที่แนะนำ: CONTRACT v1.6 → 07 (history tools) + 04 (simulate) พร้อมกัน → 03 + 02 → 01 → eval

## 8. การแก้ CONTRACT (v1.5 → v1.6)

**เพิ่มเท่านั้น ไม่ลบ / เปลี่ยนชื่อ field เดิม** ยกเว้นตาราง intent (§3) ที่ล็อกไว้ซึ่งต้องแก้ผ่าน PR นี้

| หัวข้อ | เปลี่ยนอะไร |
|---|---|
| Object ที่ใช้ร่วม · enum | `route` เพิ่ม `stats_tool` (ป้ายไทย "คำนวณจากสถิติย้อนหลัง") · `category` เพิ่ม `historical`, `simulation` · `origin` เพิ่ม `openfootball`, `fjelstul` |
| Trace | เพิ่ม field optional `tool: {name, params}` · `fallback` เพิ่ม `stats_no_tool`, `history_down`, `history_out_of_range`, `simulation_down` |
| §3 intent | เพิ่มแถว `history_stats` → `stats_tool` · `filters.category` = – (ไม่ค้น 05 ยกเว้นทางถอย) · ตัวอย่าง "แมนยูเจอลิเวอร์พูลชนะกี่ครั้ง" · classifier มี 9 หมวด |
| §3 engines | เพิ่ม `POST /local/simulate` · `/local/predict` เพิ่ม field optional `home_strength`, `away_strength`, `league_avg_goals` |
| §6 doc_id | เพิ่ม `stats-<tool>-<hash8>`, `sim-<season>-<hash8>`, `pred-<season>-<home>-<away>` (ใช้ใน Source เท่านั้น ไม่ index) และ doc_id ของ `historical` ตามที่ PR #22 เสนอ |
| §7 | เพิ่ม §7.1 `/football/history/*` (7 path) และ `/football/simulation`, `/football/simulation/what-if`, `/football/predict` |
| §1 | เพิ่ม `/api/football/simulation`, `/api/football/simulation/what-if` |
| error code | เพิ่ม `SIMULATION_UNAVAILABLE` (503) |
| Changelog | เพิ่มแถว v1.6 |

## 9. ความเสี่ยง

| ความเสี่ยง | ทางรับมือ |
|---|---|
| LLM เลือก tool ผิด / ใส่ปีผิด | ตรวจพารามิเตอร์ใน router · วัด tool accuracy ใน eval · แสดง `trace.tool` ให้เห็นบนหน้าเว็บ |
| ฟีเจอร์ 1 เพิ่ม latency (LLM เลือก tool + 06) | เลือก tool ใช้ `max_tokens` ต่ำและ `reasoning_effort` ต่ำ · 07 query ตารางย้อนหลังจาก DB ที่ index `season` / slug ไว้แล้ว |
| โมเดล Poisson ง่ายเกินไป ตัวเลขดูไม่น่าเชื่อ | แสดงผล backtest เทียบ baseline ในรายงาน · ข้อความเตือนว่าเป็นการประมาณการ |
| คำถามทำนายผลถูกใช้ไปทางพนัน | ด่าน safety ใน 06 เดิม · ไม่แสดงราคาต่อรอง · ข้อความเตือนทุกคำตอบ |
| PR ที่เป็นเงื่อนไข (§2) ยังไม่ merge | เริ่มจาก CONTRACT v1.6 และ 04 `simulate.py` (ไม่พึ่งใคร) ก่อนได้ |
