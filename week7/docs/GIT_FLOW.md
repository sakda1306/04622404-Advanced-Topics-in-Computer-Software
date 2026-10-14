# GIT_FLOW.md — คู่มือใช้ git ของทีม D-II · ผู้ช่วยฟุตบอล
### ทำตามทีละขั้น ไม่ต้องเข้าใจ git ก็ทำได้

> ส่งให้ทุกคน · **ถ้าไม่เคยใช้ git มาก่อน อ่านแค่หัวข้อ 0 ถึง 4 ก็ทำงานได้ทั้งสัปดาห์**
> หัวข้อ 5 ไว้เปิดตอนพัง · หัวข้อ 6–7 ไว้อ่านตอนปลายสัปดาห์
>
> **หลักคิดข้อเดียวที่ต้องจำ**: คุณมี branch ของตัวเอง งานคุณอยู่แค่ในนั้น จะพังยังไงก็ไม่กระทบใคร
> ของจะเข้าไปรวมกับคนอื่นก็ต่อเมื่อคุณเปิด PR และหัวหน้า (`sakda1306`) กด merge เท่านั้น

---

## 0. ตั้งค่าครั้งเดียว (10 นาที ทำวันแรกวันเดียว)

**0.1 บอก git ว่าคุณเป็นใคร** — ใช้ชื่อกับอีเมลเดียวกับบัญชี GitHub ของคุณ ไม่งั้น commit จะไม่ขึ้นชื่อคุณ และ **หลักฐานการมีส่วนร่วมของคุณจะหายไป** (อาจารย์ดูข้อนี้ และแก้ย้อนหลังไม่ได้)

```bash
git config --global user.name "ชื่อที่ใช้บน GitHub"
git config --global user.email "อีเมลที่สมัคร GitHub"
```

เช็กว่าถูก:
```bash
git config --global user.name
git config --global user.email
```

**0.2 โหลด repo ของทีมลงเครื่อง**

```bash
git clone https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D-II.git
cd Advanced-Topic-in-Computer-Software-Course-Team-D-II
```

clone มาจะได้ `main` ซึ่งเป็นเวอร์ชันสำหรับนำเสนอ **ไม่ใช่ที่ที่คุณทำงาน** ข้อ 0.4 จะพาไป branch ของคุณ

ถ้าถามรหัสผ่านแล้วใส่ไม่ผ่าน → GitHub ไม่รับรหัสผ่านแล้ว ให้ทำอย่างใดอย่างหนึ่ง
- ติดตั้ง **GitHub CLI** แล้วสั่ง `gh auth login` (ง่ายที่สุด)
- หรือสร้าง **Personal Access Token** ในหน้า GitHub Settings แล้วใช้ token แทนรหัสผ่าน

**0.3 สร้าง `.env` ของตัวเอง** (ไฟล์นี้ไม่ขึ้น git ทุกคนมีของตัวเอง)

```bash
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

เปิด `.env` แล้วเติม key **ของตัวเอง** (Groq, Gemini, football-data.org, API-Football — สมัครฟรีทั้งหมด วิธีสมัครอยู่ใน `00_PLAN_OVERVIEW.md` หัวข้อ 6 และ 10)
ถ้าต้องเพิ่มตัวแปรใหม่ ให้เพิ่ม **ชื่อตัวแปรค่าว่าง** ใน `.env.example` แล้วบอกหัวหน้าใน PR

**0.4 สร้าง branch ของตัวเอง** — ทำครั้งเดียวตอนเริ่ม ชื่อตามตารางนี้

| คุณคือ | GitHub | โฟลเดอร์ที่แก้ได้ | branch ของคุณ |
|---|---|---|---|
| 01 Web App · member1 | `Mekmai4234` | `services/01_web_app/` | `feature/01-web-mekmai4234` |
| 02 API Backend · sakda1306 | `sakda1306` | `services/02_api_backend/` | `feature/02-api-sakda1306` |
| 03 AI Router · member2 | `mahawongsupawit125-coder` | `services/03_ai_router_agent/` | `feature/03-ai-router-mahawongsupawit125-coder` |
| 04 AI Engines · member3 | `PhonlakritTH` | `services/04_ai_engines/` (branch ปัจจุบันใช้ `services/04_ai_model_selection/` · รอตัดสินชื่อ) | `feature/04-ai-model-selection-phonlakrit` |
| 05 Retrieval · sakda1306 | `sakda1306` | `services/05_retrieval_knowledge/` | `feature/05-retrieval-sakda1306` |
| 06 Generation · member4 | `cira1234` | `services/06_llm_generation/` | `feature/06-generation-cira1234` |
| 07 Football Data · member5 | `Notnrxth` | `services/07_football_data/` | `feature/07-footballdata-notnxrth` |
| Deploy & Monitoring · member6 | `Peem-Atikorn` | `deploy/`, `eval/`, `docker-compose*.yml`, `Makefile`, `.github/` | `feature/08-deploy-peem-atikorn` |

> เอกสารอื่นยังเรียกสมาชิกว่า `memberN` ใช้ตารางนี้ map กับ GitHub username
> **คนที่ถือ 2 โมดูล (sakda1306)** ใช้ 2 branch แยกกัน ให้ PR แยกกันชัดเจน อาจารย์ตรวจง่าย

```bash
git checkout develop                                  # ต้องอยู่ที่ develop ก่อน
git checkout -b feature/03-router-member2             # เปลี่ยนเป็นของคุณ
git push -u origin feature/03-router-member2
```

**บรรทัดแรกสำคัญที่สุด** — ต้องแตกจาก `develop` ไม่ใช่ `main`
ถ้าแตกจาก `main` งานคุณจะไปคนละสายกับทีม เช็กด้วย `git status` บรรทัดแรกก่อนเสมอ

**0.5 เช็กว่าอยู่ถูกที่** — พิมพ์คำสั่งนี้ทุกครั้งที่ไม่แน่ใจ
```bash
git status
```
บรรทัดแรกต้องขึ้นว่า `On branch feature/xx-...-ชื่อคุณ`
**ถ้าขึ้นว่า `On branch main` หรือ `On branch develop` แปลว่าอยู่ผิดที่ หยุดแล้วสั่ง `git checkout feature/...` ก่อนทำอะไรต่อ**

**0.6 กันไฟล์ของเครื่องมือส่วนตัวไม่ให้หลุดขึ้น git** (ทำครั้งเดียว)

ถ้าคุณใช้เครื่องมือช่วยเขียนโค้ดที่สร้างโฟลเดอร์ตั้งค่า/ความจำไว้ในโฟลเดอร์ repo ให้ใส่ชื่อโฟลเดอร์นั้นใน **`.git/info/exclude`** (มีผลแค่เครื่องคุณ ไม่ขึ้น git)
**ห้ามใส่ใน `.gitignore`** — `.gitignore` ขึ้น git และเป็นไฟล์ของทั้งทีม ต้องไม่มีชื่อเครื่องมือส่วนตัวของใคร

```bash
echo "<ชื่อโฟลเดอร์ของเครื่องมือ>/" >> .git/info/exclude
git status          # โฟลเดอร์นั้นต้องไม่โผล่แล้ว
```

---

## 1. วงจรประจำวัน — จำแค่ 3 ช่วง

### เช้า ก่อนเริ่มงาน — ดึงของกลางล่าสุดมา (สำคัญมาก)

```bash
git checkout feature/03-router-member2     # ให้แน่ใจว่าอยู่ branch ตัวเอง
git fetch origin
git merge origin/develop
```

**ทำไมต้องทำทุกเช้า** — ถ้าไม่ทำ พอถึงวันรวมงานจะมีของคนอื่นที่คุณไม่เคยเห็นเป็นร้อยไฟล์ แล้วชนกันหนักมาก ทำทุกเช้าคือทำทีละนิด ไม่เจ็บ
ถ้าขึ้นคำว่า `CONFLICT` → ข้ามไปหัวข้อ 5.1

### ระหว่างวัน — commit บ่อย ๆ ทีละนิด

ทำงานเสร็จเป็นชิ้น ๆ (ไม่ต้องรอเสร็จทั้งหมด) แล้วสั่ง 3 คำสั่งนี้

```bash
git status                                     # 1) ดูว่าแก้อะไรไปบ้าง
git add services/03_ai_router_agent/           # 2) เลือกเฉพาะโฟลเดอร์ตัวเอง
git commit -m "feat(03-router): เพิ่มกฎจับชื่อทีมจาก team aliases"
```

**ข้อควรระวังที่สำคัญที่สุด** — คำสั่ง `git add .` (จุด) หรือ `git add -A` จะเก็บทุกอย่างรวมถึงไฟล์ที่ไม่ควรเก็บ
**ให้พิมพ์ชื่อโฟลเดอร์ตัวเองเสมอ** อย่าใช้จุด

ก่อน commit ดูผลของ `git status` ว่ามีแต่ไฟล์ในโฟลเดอร์ตัวเอง ถ้าเห็นไฟล์ของคนอื่นโผล่มาแปลว่ามีอะไรผิด → หัวข้อ 5.2

### เย็น ก่อนเลิก — ตรวจ 1 นาที แล้วส่งขึ้น GitHub

**ทำ checklist ในหัวข้อ 4.1 ก่อน push ทุกครั้ง** แล้วค่อย

```bash
git push
```

**push ทุกวัน แม้งานยังไม่เสร็จ** — เพราะ
1. เครื่องพังแล้วงานไม่หาย
2. หัวหน้าเห็นว่าคุณเดินอยู่ ไม่ต้องมาทวง
3. **อาจารย์ดูว่าทุกคนมีส่วนร่วม** — commit ที่กระจายทั้งสัปดาห์ดูดีกว่าก้อนเดียววันสุดท้ายมาก

> การ push ขึ้น branch ตัวเอง **ไม่กระทบใครทั้งสิ้น** ของยังไม่เข้าส่วนกลางจนกว่าจะ merge PR

---

## 2. เปิด PR — ทำเมื่อได้ของที่ใช้งานได้จริงชิ้นหนึ่ง (อย่างน้อยวันเว้นวัน)

PR = "ขอเอาของใน branch ผมไปรวมกับส่วนกลาง" **หัวหน้าเป็นคนกด merge ไม่ใช่คุณ**

### ก่อนเปิด PR เช็กข้อเหล่านี้

```bash
git fetch origin && git merge origin/develop     # ดึงของล่าสุดมาก่อน
git diff --stat origin/develop                   # ดูว่าแก้อะไรไปบ้าง
```
- [ ] รายการที่ออกมา **มีแต่ไฟล์ในโฟลเดอร์ตัวเอง**
- [ ] ผ่าน checklist หัวข้อ 4.1 ครบ (ไม่มีความลับ ไม่มีร่องรอยเครื่องมือ AI)
- [ ] service ตัวเองรันได้ และ `GET /health` ตอบ
- [ ] ตอบ JSON ตรงตาม `docs/CONTRACT.md` (ถ้าจะแก้ contract ต้องแยกเป็นอีก PR)
- [ ] เทสของตัวเองผ่าน (`pytest` / `npm test`)
- [ ] ถ้าเพิ่ม library ใหม่ อัปเดต `pyproject.toml` / `requirements.txt` / `package.json` แล้ว **และเขียนบอกในคำอธิบาย PR**

### เปิด PR ยังไง (ทำบนเว็บ ง่ายกว่า)

1. `git push` ให้เรียบร้อย
2. เข้าหน้า repo บน GitHub จะเห็นแถบเหลือง `Compare & pull request` → กด
3. **ตรวจหัวข้อบนสุดให้ดี** ต้องเป็น
   ```
   base: develop  ←  compare: feature/03-router-member2
   ```
   **`base` ต้องเป็น `develop` ห้ามเป็น `main`** — `main` เป็น default branch ปุ่มจะเด้ง `base: main` มาให้เสมอ ต้องเปลี่ยนเองทุกครั้ง
4. ตั้งชื่อ PR แบบเดียวกับ commit เช่น `feat(03-router): cascade ชั้น rules + classifier`
5. ในช่องคำอธิบาย เขียน 3 อย่าง: **ทำอะไรไป / ทดสอบยังไง / มี library ใหม่ไหม**
6. กด **Create pull request**
7. **ไปบอกในกลุ่มว่าเปิด PR แล้ว** หัวหน้าจะได้มารีวิว

### แล้วรออะไร

| ผลรีวิว | คุณต้องทำอะไร |
|---|---|
| **Approve** → หัวหน้ากด merge | ไปทำงานต่อได้เลย (เช้าวันถัดไปอย่าลืม `git merge origin/develop`) |
| **Comment** ถามคำถาม | ตอบในคอมเมนต์ ไม่ต้องแก้โค้ดถ้ายังไม่ได้ตกลงกัน |
| **Request changes** ขอให้แก้ | ดูหัวข้อ 3 |

**ระหว่างรอรีวิว ไม่ต้องหยุดทำงาน** — ทำงานต่อใน branch เดิมได้เลย

> PR ของหัวหน้าเอง (02, 05) ให้ **member6 เป็นคนรีวิว** และหัวหน้ากด merge หลังได้ approve

---

## 3. โดนขอให้แก้ ทำยังไง

**ไม่ต้องเปิด PR ใหม่** PR เดิมจะอัปเดตตัวเองอัตโนมัติเมื่อคุณ push เพิ่ม

```bash
# แก้โค้ดตามที่เขาบอก แล้ว
git add services/03_ai_router_agent/
git commit -m "fix(03-router): ใส่ timeout ให้ทุก call ตาม CONTRACT §0"
git push
```

แล้วไปตอบในคอมเมนต์ว่าแก้แล้ว หัวหน้าจะมาดูรอบสอง

---

## 4. กฎ 7 ข้อที่ห้ามละเมิด

| # | กฎ | ถ้าละเมิดจะเกิดอะไร |
|---|---|---|
| 1 | **แก้ได้เฉพาะโฟลเดอร์ของตัวเอง** (ตารางหัวข้อ 0.4) | ทับงานเพื่อนแล้วเขาไม่รู้ตัว |
| 2 | **ห้าม `git push` ตรงเข้า `main` หรือ `develop`** เข้าผ่าน PR เท่านั้น | ของพังเข้าส่วนกลาง ทุกคนพังตาม |
| 3 | **เจอบั๊กในงานคนอื่น → เปิด Issue แท็กเจ้าของ ห้ามแก้เอง** | เจ้าของไม่รู้ว่าของตัวเองพัง แล้วพังซ้ำที่เดิม |
| 4 | **ห้าม commit `.env`, API key, ไฟล์โมเดล, FAISS/BM25 index, ไฟล์ข้อมูลที่ดึงจาก API, ไฟล์เกิน 5 MB** | key หลุด (ต้องยกเลิกแล้วออกใหม่) / repo อืด / ผิดเงื่อนไขผู้ให้บริการข้อมูล |
| 5 | **ห้ามแก้ `docs/CONTRACT.md` เอง** ถ้าคิดว่าผิด ทักในกลุ่ม แล้วแก้ผ่าน PR แยกที่หัวหน้า + คนที่เกี่ยวข้องอนุมัติ | คนอื่นเขียนโค้ดตาม contract เดิมอยู่ พังหมด |
| 6 | **ห้ามมีร่องรอยเครื่องมือ AI ในงาน** — ไม่มีลายน้ำ ไม่มีบรรทัด `Co-Authored-By` ของ AI ไม่มีข้อความ "generated with ..." ไม่มีชื่อผู้ช่วย AI หรือบริษัทผู้ทำ ใน commit message, คำอธิบาย PR, README, คอมเมนต์ในโค้ด, `.gitignore` และห้าม commit โฟลเดอร์/ไฟล์ตั้งค่าของเครื่องมือพวกนั้น (ใช้ `.git/info/exclude` ตามข้อ 0.6) | เป็นกฎเหล็กของทีม · AI ต้องไม่ขึ้นเป็น author / contributor ของ repo |
| 7 | **ทำ checklist 4.1 ก่อน push ทุกครั้ง ไม่มีข้อยกเว้น** | ของที่ push ขึ้นไปแล้ว ลบออกจากประวัติยากมาก |

> หมายเหตุกฎ 6: คำว่า AI ที่เป็น **เนื้องานของระบบ** (เช่น "AI Router", "General AI", ชื่อโมเดลใน config) ไม่ผิดกฎ — กฎนี้ห้ามเฉพาะร่องรอยของ **เครื่องมือที่ใช้ช่วยเขียนงาน**

### 4.1 Checklist ก่อน push (ทุกครั้ง · 1 นาที)

```bash
git status                                   # 1) ไม่มี .env, ไม่มีโฟลเดอร์ตั้งค่าเครื่องมือ, มีแต่โฟลเดอร์ตัวเอง
git diff --cached --stat                     # 2) ไฟล์ที่จะ commit ตรงกับที่ตั้งใจ
git log origin/develop..HEAD --format=%B     # 3) อ่าน commit message ที่ยังไม่ขึ้น — ต้องไม่มี trailer ของ AI
git diff origin/develop --name-only          # 4) รายชื่อไฟล์ทั้งหมดที่ต่างจากส่วนกลาง
git grep -n -i -E "co-authored-by|generated with" -- $(git diff origin/develop --name-only)
                                             # 5) ต้องไม่เจออะไรเลย
```

- [ ] ข้อ 1–4 ไม่มีไฟล์แปลกปลอม ไม่มี `.env` ไม่มี key
- [ ] ข้อ 3 ไม่มีบรรทัด `Co-Authored-By` ของ AI หรือข้อความ "generated with"
- [ ] ข้อ 5 ไม่เจออะไร (ยกเว้นบรรทัดที่อธิบายกฎนี้ใน `docs/GIT_FLOW.md` เอง) และค้นชื่อเครื่องมือ AI ที่ตัวเองใช้เพิ่มด้วย (`git grep -n -i "<ชื่อเครื่องมือ>"`)
- [ ] **ไม่ใช้ `git push --tags` หรือ `--follow-tags`** (tag สร้างโดยหัวหน้าตอน release เท่านั้น)

เจอข้อไหนผิด → **อย่า push** แก้ตามหัวข้อ 5.3 / 5.4 ก่อน

### รูปแบบ commit message

```
<type>(<เลข>-<โมดูล>): <ทำอะไร>
```

ตัวอย่างที่ถูก
```
feat(05-retrieval): upsert เอกสารตาม doc_id ให้ BM25 กับ FAISS ตรงกัน
feat(07-footballdata): ดึง standings จาก football-data.org ทุก 6 ชม.
fix(02-api): คืน 504 ROUTER_TIMEOUT เมื่อ router เกิน 45s
test(03-router): เพิ่มเคสทดสอบ route 40 ข้อ
docs(06-generation): อธิบาย prompt รายงานประจำสัปดาห์
```

`type` ที่ใช้ได้: `feat` `fix` `test` `docs` `refactor` `chore`
ห้ามเขียน: `update`, `fix bug`, `asdf`, `งานวันนี้`, หรือ commit ทั้งวันรวมเป็นก้อนเดียว
**commit message มีแค่หัวเรื่อง (และคำอธิบายถ้าจำเป็น) — ไม่มี trailer หรือลายเซ็นใด ๆ ต่อท้าย**

---

## 5. เมื่อพัง — เปิดหัวข้อนี้

> **กฎเหล็กเวลาตกใจ: อย่าลบโฟลเดอร์ทิ้งแล้ว clone ใหม่** งานที่ยังไม่ push จะหายถาวร
> ทักในกลุ่มก่อนเสมอ ถ่ายรูปข้อความ error มาด้วย

### 5.1 ขึ้นคำว่า CONFLICT ตอน merge

แปลว่าคุณกับคนอื่นแก้ไฟล์เดียวกัน git เลยไม่รู้จะเอาของใคร

```bash
git status          # ดูว่าไฟล์ไหนชน
```

- **ถ้าไฟล์ที่ชนอยู่ในโฟลเดอร์ของคุณ** → เปิดไฟล์นั้น จะเห็น
  ```
  <<<<<<< HEAD
  โค้ดของคุณ
  =======
  โค้ดที่มาจาก develop
  >>>>>>> origin/develop
  ```
  ลบเครื่องหมาย 3 บรรทัดนั้นออก เก็บโค้ดที่ถูกต้องไว้ แล้ว
  ```bash
  git add <ไฟล์ที่แก้>
  git commit
  ```
- **ถ้าไฟล์ที่ชนอยู่ในโฟลเดอร์ของคนอื่น หรือเป็น `docker-compose.yml` / `Makefile` / `docs/CONTRACT.md`**
  → **หยุด อย่าแก้** สั่งยกเลิกแล้วทักหัวหน้า
  ```bash
  git merge --abort
  ```

### 5.2 เผลอแก้ไฟล์ของคนอื่น ยังไม่ commit

```bash
git restore <path/ไฟล์นั้น>        # คืนค่าไฟล์เดียว
```

### 5.3 เผลอ commit ไปแล้ว (ไฟล์ผิด หรือ message ผิด) แต่ยังไม่ push

```bash
git reset --soft HEAD~1       # ถอย commit ล่าสุด โค้ดยังอยู่ครบ
```
แล้ว `git add` ใหม่เฉพาะโฟลเดอร์ตัวเอง และ commit ใหม่ด้วย message ที่ถูก

### 5.4 เผลอ commit ไฟล์ที่ไม่ควร (`.env`, ไฟล์ใหญ่, ไฟล์ตั้งค่าเครื่องมือ) แต่ยังไม่ push

```bash
git reset --soft HEAD~1
git restore --staged .env      # เอาออกจากคิว ไฟล์ยังอยู่ในเครื่อง
git add services/<ของคุณ>/
git commit -m "..."
```

**ถ้า push ไปแล้วและมี API key อยู่ในนั้น → ทักในกลุ่มทันที** ต้องยกเลิก key ตัวนั้นแล้วออกใหม่ ลบ commit อย่างเดียวไม่พอ
**ถ้า push ไปแล้วและมีร่องรอยเครื่องมือ AI** → ทักหัวหน้า ห้ามแก้ประวัติเอง (ห้าม force push)

### 5.5 อยู่ผิด branch แล้วเขียนโค้ดไปแล้ว ยังไม่ commit

```bash
git stash                                   # เก็บงานพักไว้
git checkout feature/03-router-member2      # ย้ายไป branch ที่ถูก
git stash pop                               # เอางานกลับมา
```

### 5.6 push แล้วขึ้นว่า rejected / non-fast-forward

แปลว่าบน GitHub มีของใหม่กว่าในเครื่องคุณ

```bash
git pull --no-rebase
# ถ้ามี conflict ให้ทำตามข้อ 5.1 แล้ว
git push
```

### 5.7 อยากรู้ว่าตัวเองแก้อะไรไปบ้าง

```bash
git status                        # ไฟล์ที่แก้แต่ยังไม่ commit
git log --oneline -10             # 10 commit ล่าสุด
git diff --stat origin/develop    # ต่างจากส่วนกลางยังไงบ้าง
```

### 5.8 อยากทิ้งทุกอย่างในเครื่อง กลับไปเหมือนบน GitHub

> **งานที่ยังไม่ commit จะหายถาวร** ใช้เมื่อแน่ใจจริง ๆ เท่านั้น

```bash
git fetch origin
git reset --hard origin/feature/03-router-member2
```

---

## 6. โครง branch ของทีม (ไว้อ่านเข้าใจภาพรวม)

```
main        ← เวอร์ชันสำหรับนำเสนอ · หัวหน้า merge จาก develop เท่านั้น (D6)
  ↑
develop     ← จุดรวมงานของทุกคน · เข้าได้ผ่าน PR เท่านั้น ห้าม push ตรง
  ↑  ↑  ↑
feature/01-web-member1   feature/02-api-sakda1306   feature/05-retrieval-sakda1306   ...
```

**ใครแก้อะไรได้** (บังคับด้วยไฟล์ `.github/CODEOWNERS` + branch protection ไม่ใช่ความจำ · CODEOWNERS มีแล้ว จะบังคับจริงเมื่อเปิด "Require review from Code Owners" ใน branch protection ของ `develop`)

| คน | แก้ได้ |
|---|---|
| แต่ละคน | `services/<โฟลเดอร์ตัวเอง>/` ทั้งหมด **ยกเว้น** `Dockerfile` |
| member6 (Deploy & Monitoring) | `docker-compose*.yml`, `.env.example`, `Makefile`, `deploy/`, `eval/`, `.github/workflows/`, `services/*/Dockerfile` |
| หัวหน้า (sakda1306) | ทุกอย่างข้างบน + `.github/CODEOWNERS`, `README.md` ราก, `docs/` |
| `docs/CONTRACT.md` | ต้องได้ approve จากหัวหน้า + เจ้าของ service ทั้งสองฝั่งที่เกี่ยวข้อง |

**branch protection ที่หัวหน้าตั้งใน D1**
- `main`: ต้องผ่าน PR + approve 2 คน + CI ผ่าน · ห้าม force push
- `develop`: ต้องผ่าน PR + approve 1 คน (เจ้าของโฟลเดอร์ตาม CODEOWNERS) + CI ผ่าน · ห้าม force push

---

## 7. ส่งงานเข้า repo ส่วนตัวของตัวเอง (ทำปลายสัปดาห์ D6)

ได้ **เฉพาะโค้ดในโฟลเดอร์ตัวเอง พร้อมประวัติ commit ของตัวเอง** ไม่ติดงานเพื่อนมาด้วย

```bash
# 1) ใน clone ของ repo ทีม อยู่บน branch ตัวเองที่อัปเดตแล้ว
git branch -f export/03 $(git subtree split --prefix=services/03_ai_router_agent HEAD)

# 2) ไปที่ repo ส่วนตัวของคุณ
cd /path/to/repo-ส่วนตัว
git remote add team /path/to/โฟลเดอร์-repo-ทีม-ในเครื่อง     # ครั้งแรกครั้งเดียว
git fetch team export/03
git subtree add  --prefix=DL06 team export/03               # ครั้งแรก
git subtree pull --prefix=DL06 team export/03               # ครั้งถัดไป
```

ก่อน `git push` ใน repo ส่วนตัว **ทำ checklist 4.1 อีกรอบ** แล้วค่อย push
เปลี่ยน `03`, ชื่อโฟลเดอร์ และ `DL06` ให้ตรงกับของคุณ · **ติดตรงไหนถามหัวหน้า อย่าเดา**

---

## สรุปที่ต้องจำจริง ๆ แค่นี้

```bash
# เช้า
git checkout feature/xx-ของคุณ && git fetch origin && git merge origin/develop

# ระหว่างวัน ทำเสร็จเป็นชิ้น ๆ
git status
git add services/xx_ของคุณ/
git commit -m "feat(xx-โมดูล): ทำอะไรไป"

# เย็น — checklist 4.1 ก่อน แล้วค่อย
git push
```

**ได้ของที่ใช้งานได้ → เปิด PR เข้า `develop` → บอกในกลุ่ม → รอหัวหน้ารีวิว**
**พังเมื่อไหร่ → เปิดหัวข้อ 5 → ไม่เจอคำตอบ → ทักในกลุ่มพร้อมรูป error อย่าเดาเอง**
