# CareerMirror: Design System

<!--
PURPOSE: All UI rules: tokens, components, layout, states, accessibility, Thai copy rules.
Colours and fonts come from CIBrand.md; reference them by name, do not copy hex values or font names.
DOES NOT CONTAIN: architecture (Design.md), brand definitions (CIBrand.md).
OWNER: frontend lead.
-->

Brand source: [CIBrand.md](CIBrand.md) · Visual reference: [brand book](brand/CareerMirror_BrandBook_MistSlate.pdf) · Data shapes shown in components: [Contract.md](Contract.md)

Every design follows the brand book. If a rule here differs from the brand book, the brand book wins and this file is updated to match.

Status: DRAFT. Items marked (assumed) are proposals, not yet confirmed by the team.

## 1. Tokens

Stack: Next.js 16 App Router in JavaScript (`.js` / `.jsx`) + Tailwind CSS 4. Tailwind 4 has no `tailwind.config.js`: the tokens live in `web/app/globals.css`, light values in its `@theme` block and dark values in `.dark`; the default Tailwind colour palette is switched off, so only brand colours exist as utilities. The class on `<html>` is set by `next-themes` (see 1.4). Utility names are listed in `web/README.md`. Components may start from shadcn/ui (Radix primitives, accessible by default) and are restyled with these tokens.

### 1.1 Colour tokens

Each token points to a **named** colour in CIBrand.md section 3. CIBrand.md defines a light and a dark value for every name; the hex values live only there. Components use the tokens only, never hex values or Tailwind `dark:` colour overrides, so a component looks right in both themes without theme-specific code.

| token | CIBrand colour name | use |
|---|---|---|
| `--color-primary` | Primary | main buttons, links, active tab, meter fill |
| `--color-primary-hover` | Primary Dark | hover / pressed (darker in light theme, lighter in dark theme) |
| `--color-on-primary` | On Primary | text and icons on Primary buttons |
| `--color-primary-subtle` | Primary Light | selected chip, highlighted card background |
| `--color-accent` | Accent | match % emphasis, highlights (sparingly) |
| `--color-bg` | Neutral 0 | page background |
| `--color-surface` | Neutral 50 | cards, sidebar |
| `--color-border` | Neutral 200 | dividers, input borders |
| `--color-text` | Neutral 900 | body text |
| `--color-text-muted` | Neutral 600 | captions, sources, dates |
| `--color-success` | Success | matched skills, saved state |
| `--color-warning` | Warning | missing skills, stale data, quota low |
| `--color-danger` | Danger | errors, destructive actions |
| `--color-info` | Info | notices, disclaimers |

Colour is never the only signal: matched / missing skills also use an icon and a text label.

### 1.2 Typography tokens

| token | CIBrand font | size / line height | use |
|---|---|---|---|
| `--font-thai` | Thai font | – | all Thai text |
| `--font-latin` | Latin font | – | numbers, English skill names (fallback after the Thai font) |
| `text-display` | | 32 / 44 px, weight 700 | landing headline |
| `text-h1` | | 28 / 40, 700 | page title |
| `text-h2` | | 22 / 32, 600 | section title |
| `text-h3` | | 18 / 28, 600 | card title |
| `text-body` | | 16 / 26, 400 | default |
| `text-small` | | 14 / 22, 400 | captions, sources |
| `text-tiny` | | 12 / 18, 500 | chips, badges (never for body copy) |

Thai needs taller line height than Latin text; keep the ratios above. `font-family: var(--font-thai), var(--font-latin), system-ui, sans-serif`.

### 1.3 Spacing, radius, shadow, motion

- Spacing scale (4 px base): 4, 8, 12, 16, 24, 32, 48, 64.
- Radius (brand book): `--radius-sm` 8 px (inputs, small badges) · `--radius-md` 12 px (buttons) · `--radius-lg` 16 px (cards, dialogs, chat bubbles) · `--radius-xl` 20 px (hero and gradient panels) · full for pills (skill chips, the theme toggle options).
- Shadow: `--shadow-sm` for cards, `--shadow-md` for popovers and dialogs. No shadow on flat list items. In the dark theme shadows are barely visible, so cards also get a 1 px `--color-border` edge and use `--color-surface`, which is lighter than the page.
- Surfaces (brand book): frosted-glass cards (backdrop blur 10 px) appear **only on brand-gradient areas**: the landing hero and empty states. Light theme: white at 70–85% opacity with a 1 px white edge and a soft shadow. Dark theme: `--color-surface` at 75–85% opacity with a 1 px Primary edge at 14% opacity. Working screens (every page except the landing: login, register, intake, profile, roles, account, admin) sit on a dimmed, slow silk background (`components/app/app-background.js`: deep navy in dark, pale mist in light, at 45% of the landing silk's speed). Their `--color-surface` cards (1 px `--color-border` edge) become frosted, see-through panels on it (Surface at 55–62% opacity, 16 px backdrop blur); login and register drop their own gradient for it.
- Motion: 150 ms ease-out for hover/focus, 250 ms for panels. Respect `prefers-reduced-motion` (no animation of the meter or skeletons). Exits are shorter than entrances (about 60–70%). At most one or two things move at once on a screen.
- Motion settings live in `web/lib/motion.js`; change a value there, not in components.
  - **Page transition** (currently off for page changes: `TRANSITION_PAGES` is empty, so links, back/forward and the register/login success screen change page directly; only Generate profile shows the panel. When pages are listed there, it runs between them, started by link clicks, back/forward and `navigate()` from code): dots stream in from the left and right edges, each row at its own pace, and swell into tiles until the screen is filled with the curtain colour (520 ms); the page then stays fully covered, with the twinkling dot grid, for at least **500 ms** (`PAGE_TRANSITION.minHold`, counted once filled) and until the new page is ready; then the tiles shrink back into dots that stream out to the sides (460 ms). Fill settings: `DOT_CURTAIN`. A page that loads data keeps the panel up with `usePageReady(false)` until its data arrives. The panel lifts after 8 s at most so a stuck page shows its own loading or error state. While it is up the page takes no clicks or focus (`inert`); afterwards focus moves to the new `<h1>`. The new page never shows before the screen is filled: link clicks and `navigate()` change the page only once covered, and after browser back/forward (which changes the page at once) the page stays hidden until covered. A link with `data-transition="off"` skips it (in-page anchors). Reduced motion: the filled curtain fades in and out instead, same timing.
  - **Success message** (register, login; shown only when those pages are in `TRANSITION_PAGES`): the same panel shows a drawn check, "สมัครสมาชิกสำเร็จ" / "เข้าสู่ระบบสำเร็จ" and the user's name for 900 ms; any tap or key skips the extra time.
  - **Generate profile**: the panel shows the user's character being built in a mirror, one part about every 260 ms, with the real stages below it (request running → profile page loading); it stays at least 1.5 s and until `/profile` has loaded.
  - **Dot grid** (landing hero, privacy band, final call to action, transition panel): a canvas of dots 8 px apart; each dot twinkles on its own (random 2–6 s cycle, about 12% sparkle brighter), dense at the left and right edges and fading towards the middle and the bottom, so text contrast is set by the gradient alone. About 30 fps; pauses off-screen and in hidden tabs; one still frame with reduced motion. Colour `--dot-color` (#9fd9c6).
  - **Silk background** (landing hero, privacy band, final call to action): a slow WebGL "silk" shader (`components/ui/shader-background.js`) in brand colours (deep navy folds, teal-to-mint highlight) under the hero scrim and the dot grid. It pauses off-screen and in hidden tabs, draws one still frame with reduced motion, and falls back to the brand gradient without WebGL.
  - **Chat popover**: opens from the chat button in about 260 ms with a slight overshoot, closes in 160 ms.
  - **Lists**: items that appear together (skill chips) fade up one after another, 40 ms apart, once.

### 1.4 Themes (PRD FR-36 to FR-39)

- Two themes, light and dark, plus "follow system". Default: follow system (`prefers-color-scheme`).
- Implementation: `next-themes` with `attribute="class"`, `defaultTheme="system"`, `enableSystem`, `disableTransitionOnChange`. It stores the choice in `localStorage` and sets the class before first paint, so there is no flash of the wrong theme. Nothing is sent to the API.
- Set `color-scheme: light` / `dark` on `<html>` so native controls (scrollbars, date pickers) match.
- Theme-aware assets: the logo swaps between `logo-light.svg` and `logo-dark.svg`; chart colours read the tokens; the brand gradient has a light and a dark version (CIBrand.md section 3).
- Large light-weight numbers (300) are allowed in the light theme only; use 400 or heavier in dark.

### 1.5 Charts

- Library: **Recharts 3** (SVG, so colours come straight from the tokens and switch with the theme; React 19 support; tooltips and animation built in). Plain HTML and CSS for meters, share bars and the work-style rows.
- Colours: `--color-chart-you` for the user's data, `--color-chart-ref` for the role or reference value (dashed line or outline). Status colours only for status, with an icon and text. At most 2–3 series per chart; no pie or donut charts; one value axis per chart.
- Which chart for which data:

| data | chart | notes |
|---|---|---|
| Skill overlap, user vs role | radar, 2 series on a fixed 0–4 scale | one axis per required skill or any-of group, in the role's order; 5–8 axes; the Required skill list carries the exact values; soft skills stay off the radar |
| Match % and completeness | big number + meter | number counts up with the bar |
| Why the score | horizontal stacked bars: points earned out of each part's maximum (70 / 15 / 10 / 5) | shared scale, so required skills visibly dominate |
| Salary | range bars on one ฿ axis; the official figure as a diamond | source, measure and date under the chart and in the tooltip |
| Work style, user vs role | dumbbell rows between the two ends of each trait | with the work-style disclaimer |
| Trending skills | horizontal bars, sorted, count at the end | "ข้อมูลกรุงเทพฯ" in the subtitle; the label column is as wide as the longest name (up to 180 px), longer names wrap to two lines then end in "…" (full name in the tooltip and table); skills the user has get a check and bold label, with "คุณมีแล้ว N จาก M ทักษะ" in the legend |
| Admin | stat tiles, usage meters (warning from 80%), share bars, line chart with a 7 / 30-day switch | – |

- Every chart sits in a chart card with a title, a legend when there are 2 or more series, a tooltip on hover, and a "แสดงเป็นตาราง" switch that shows the same numbers as a table.
- Motion: one grow-in of 800 ms, ease-out, when the chart first appears; bars and markers start from zero or the middle, numbers count up. With `prefers-reduced-motion` the final values show at once. Chart data is kept stable between renders so charts do not replay their animation.
- Examples with mock data: `/examples/charts` in the web app.

## 2. Layout

- Breakpoints: `sm` 640, `md` 768, `lg` 1024, `xl` 1280 px. Mobile-first.
- Content max width 1120 px, side padding 16 px (mobile) / 24 px (≥ `md`).
- **App shell**: top bar (app name from `APP_NAME`, step indicator, quota indicator, theme toggle, account menu; the account menu also shows the current theme) + content. Landing, Register and Login show a slim top bar with the app name and the theme toggle, plus buttons that depend on the session (checked without redirecting): signed out, "เข้าสู่ระบบ" and "สมัครใช้งาน" (not the one for the page you are on; on a phone the landing bar keeps only "สมัครใช้งาน"); signed in, the "เส้นทางของฉัน" menu and the account menu. **"เส้นทางของฉัน"** (signed in, on every page): one top-bar button that opens the steps 1 ข้อมูลของคุณ (`/start`), 2 โปรไฟล์ (`/profile`) and 3 สายงานที่เหมาะ (`/roles`) with a short line each; the current step is marked, and steps 2–3 are locked ("สร้างโปรไฟล์ในขั้นที่ 1 ก่อน") until a profile exists, as in the step indicator. On a phone the button shows only its icon and the menu spans the screen width.
- **Intake page**: two columns at `lg`: main area (tabs CV / แบบสอบถาม / แชท) and a right **progress sidebar** 320 px, sticky. Below `lg` the sidebar collapses into a bar above the content showing the score; tap to expand.
- **Results pages**: single column of cards; role cards in a 2-column grid at `lg`.
- Step indicator (always visible after login): 1 ข้อมูลของคุณ → 2 โปรไฟล์ → 3 สายงานที่เหมาะ → 4 รายละเอียดสายงาน.

## 3. Components

Each component lists purpose, variants and states. All interactive components have default, hover, focus-visible, active, disabled states.

| component | purpose | variants | states and rules |
|---|---|---|---|
| **Button** | actions | primary, secondary (outline), ghost, danger | loading shows spinner + keeps width; disabled has a reason in a tooltip (e.g. why "สร้างโปรไฟล์" is disabled) |
| **Input / Select** | forms | text, email, password, select, multi-select | error text under the field in Thai; label always visible (no placeholder-only labels). Desired salary is a single choice of ranges in the questionnaire (`go_salary`), not a slider |
| **File upload (CV)** | upload PDF | drop zone + button | idle, dragging, uploading (progress), parsed, error (`CV_INVALID_TYPE`, `CV_TOO_LARGE`, `CV_UNREADABLE` with the API `message_th`); shows "PDF ไม่เกิน 5 MB" |
| **Parsed CV review** | confirm/correct extracted data (FR-3) | editable list: skills, education, experience | each row editable and removable; "ยืนยันข้อมูล" primary button |
| **Questionnaire item** | one question | single, multi, scale 1-5 with end labels, skill checklist with level, text | saved indicator per item (auto-save, FR-6); optional questions marked "(ไม่บังคับ)"; a `multi` question with `max_choices` shows "เลือกได้ไม่เกิน 3 ข้อ" and disables the other options once the limit is reached (the API rejects more with `VALIDATION_ERROR`); the location question (`go_location`) shows the note "ข้อมูลตำแหน่งงานและเงินเดือนในแอปมีเฉพาะกรุงเทพฯ", because the answer is saved as a goal and does not filter roles (Design section 6); a `multi` question with 9 or more options (the IT roles) gets a search box: matches are highlighted (ring + bold matched text) and the first one scrolls into view, nothing is hidden, Enter picks the first match, and the chosen options repeat in a "เลือกแล้ว" row |
| **Chat bubble** | messages | user, assistant, system notice | assistant bubbles render citations `[1]` as Evidence citation; long answers collapse after 12 lines |
| **Chat input** | send message | – | Enter sends, Shift+Enter new line; disabled with quota message when `exhausted`; 1000-char counter |
| **Edit proposal card** | confirm a chat edit (FR-27) | inline in chat; restore variant | shows "เดิม → ใหม่" per change; buttons ยืนยัน / ยกเลิก; a proposal expires 15 min after it is made (`expires_at`): the card shows "ยืนยันได้ภายใน 15 นาที", then greys out with "หมดเวลา กรุณาพิมพ์คำขออีกครั้ง"; when a change has `restores_removed_skill`, the card says "เพิ่มทักษะที่คุณเคยลบกลับมา" so the user knows it undoes a removal (FR-31) |
| **Progress sidebar / completeness meter** | FR-9, FR-14 | – | ring or bar 0-100 with the number; checklist of slots (done ✓ / missing •) with points; slots with `required: true` (hard skills with levels, experience) are marked "จำเป็น" and listed first; while `missing_required` is not empty, the sidebar names those slots first, then `missing_th`; CV and questionnaire marked "ไม่บังคับ" when skipped, never red; "สร้างโปรไฟล์" button enabled only when `can_generate`, and its disabled tooltip names the missing required slots |
| **Skill chip** | skill in profile (FR-29) | hard, soft; matched, missing, below-level (in role cards) | on the profile, chips are grouped by level, 4 เชี่ยวชาญ down to 1 เริ่มต้น, under a summary bar of each level's share; empty levels are not shown; level dots (1-4); badge "แก้ไขโดยคุณ" when `edited_by_user` (FR-33); remove button (×) that opens a confirm dialog before removing (PRD open question 7); missing = warning colour + icon + "ยังไม่มี" |
| **Required skill list** | required skills in Role detail (`RoleDetail.required`) | single skill, any-of group | one row per requirement with the target level (dots) and weight (1-3 shown as "สำคัญมาก / สำคัญ / ควรมี"); a group with more than one skill shows them joined by " / " with the label "มีอย่างใดอย่างหนึ่ง" (for example "Python / Java / Node.js"); the user's matching skill in the group is highlighted with the matched style |
| **Evidence citation** | show where a claim comes from (FR-16) | inline `[n]` | click/hover opens a popover with `label_th` and the excerpt; keyboard focusable |
| **Role match card** | one role result | normal, below-threshold (closest role) | title, career-stage badge (`career_stage` from `GET /api/roles`: "เริ่มต้น" / "ระดับกลาง" / "อาวุโส"), match % (large number + bar), top matched skills, gaps, reason with citations, up to 5 next steps each linked to its gap, "ดูรายละเอียด" button; for a `mid` or `senior` role, a short note says the role usually needs work experience, which explains a lower score for a fresh graduate (Design section 6); `explanations_stale` shows "กำลังอัปเดตคำอธิบาย" with a refresh action |
| **Salary range** | FR-21, FR-22f | advertised, curated reference, official baseline (always separate rows) | "฿35,000 – ฿55,000 / เดือน" + source + measure + date; advertised row also shows sample size; never a single figure; the section title carries the label "ข้อมูลกรุงเทพฯ" (`location_scope: "bangkok"`) |
| **Market demand** | FR-22, FR-22f | – | posting count, trending skills as chips, list of up to 5 listings (title, company, salary text, posted date, link); the section title carries the label "ข้อมูลกรุงเทพฯ" |
| **Data freshness badge** | FR-22b, FR-22d | fresh, stale, refreshing, unavailable | fresh: "อัปเดตล่าสุด 3 พ.ย. 2569" from `fetched_at`; stale (`stale: true`): warning colour + "ข้อมูลอาจไม่เป็นปัจจุบัน" with the date; refreshing (`refreshing: true`): small spinner + "กำลังอัปเดตข้อมูล", and the page polls `GET /api/roles/{role_id}/market` every 5 s until it is false; unavailable (`available: false`): "ยังไม่มีข้อมูลตลาดงานสำหรับสายงานนี้" in place of salary, demand and listings (with the spinner if `refreshing` is true). The user cannot start a refresh; a scheduled job does it |
| **Quota indicator** | FR-25 (P1) | top bar | "เหลือ 12/40 ครั้งวันนี้" from `requests_limit − requests_used` (limit 40 per day, `QUOTA_DAILY_REQUESTS`); warning when < 20 %; exhausted shows reset time from `reset_at` |
| **Theme toggle** | switch light / dark (FR-36) | icon button in the top bar that opens a menu: สว่าง, มืด, ตามระบบ | icon shows the active theme (sun, moon, monitor); selected option has a check; accessible name "เปลี่ยนธีม"; works before login; no animation on switch; after login the account menu also lists "ธีม" with the current choice and the same three options |
| **Toast** | short feedback | success, info, warning, error | auto-hide 5 s except errors |
| **Dialog** | confirm destructive actions | – | delete account requires typing "DELETE"; focus trapped; Esc closes |
| **Skeleton / loading** | waiting | text lines, card | used for LLM waits; after 5 s add "กำลังวิเคราะห์ อาจใช้เวลาสักครู่" |
| **Empty state** | nothing yet | – | icon + one sentence + one action (e.g. "ยังไม่มีโปรไฟล์ เริ่มจากอัปโหลด CV หรือทำแบบสอบถาม") |
| **Error state** | failed request | inline, page | show `message_th` from the API; retry button; show `request_id` small and copyable for bug reports |
| **Stat tile** | one admin number (FR-43) | normal, warning | label (Thai), large value in `text-h1` with tabular figures, unit, optional delta or limit ("ใช้ไป 142,300 / 200,000"); warning state = warning colour + icon + short reason; never colour alone |
| **Usage meter** | used vs. limit (LLM tokens and requests, Apify runs, quota) | normal, warning (≥ 80%), over (100%) | bar with the number and % as text; same bar style as the completeness meter; `role="progressbar"` |
| **Share bars** | parts of a whole (routes, router layers, input mix) | – | horizontal bars sorted by size with the % at the end, Primary fill on a `--color-border` track; no pie charts |
| **Admin table** | per-role cache rows (FR-43d) | – | columns: สายงาน, อายุข้อมูล, สถานะ, ประกาศงาน, มีเงินเดือน %, เงินเดือนอ้างอิง, ข้อผิดพลาดล่าสุด; sortable; stale and error rows use the Data freshness badge; numbers right-aligned |
| **Warning list** | top of `/admin` (FR-44) | – | one row per `warnings[]` item with the panel name and `message_th`; empty state "ทุกอย่างปกติ" with a success icon |
| **Disclaimer note** | required notices | work-style, unofficial data, team-curated | info colour, small text, always next to the content it qualifies |

## 4. Page templates

| page | route (web) | content |
|---|---|---|
| Landing | `/` | what the app does (self-understanding first), how it works in 4 steps, privacy summary, buttons สมัครใช้งาน / เข้าสู่ระบบ; when signed in they become ดูโปรไฟล์ของฉัน / สายงานที่เหมาะกับฉัน (or เริ่มสร้างโปรไฟล์ / บัญชีของฉัน before a profile exists) with a welcome-back line, and the final call to action leads to the profile or step 1 |
| Register / Login | `/register`, `/login` | email, password, display name; consent checkbox with the consent notice (required); link between the two pages |
| Intake | `/start` | tabs CV / แบบสอบถาม / แชท + progress sidebar; user may use tabs in any order (PRD §5) |
| Profile | `/profile` | bento dashboard: a grid of tiles on the left and a column on the right (stacked below `lg`). Left: KPIs ทักษะด้านเทคนิค / ทักษะการทำงานร่วมกับผู้อื่น / ประสบการณ์รวม; skill strength (each technical skill as a 4-step level bar, strongest first, level in text); skills per level (grouped columns, technical and teamwork, legend + counts); the six work-style trait tiles (open for the full sentence); a strengths card (top skills at level 3+, share of strong skills, button "ดูสายงานที่เหมาะ"); สิ่งที่ยังควรสำรวจ and experience (claims with citations). Right: the work-style character (avatar; a first-person line in the character's voice built from the user's three clearest work-style leanings, e.g. "ฉันชอบลุยงานไปพร้อมทีม … และชอบเป็นคนพาทีมไปข้างหน้า", with their citations; trait chips, where a balanced trait names its topic; disclaimer always visible) and evidence sources (count + strip by CV / questionnaire / chat). Below: skill management tiles (chips grouped by level, remove with confirm) and the removed list (restore). Shared tile pieces live in `components/app/bento.js` |
| Role results | `/roles` | heading with threshold explanation; "สายงานที่คุณเลือกไว้" (the roles picked in the questionnaire, always shown with their match % and "ขาดอีก N ทักษะ" linking to the role's gaps; star + "เป้าหมายของคุณ" on their cards); role match cards (top 5); below-threshold banner when none pass (FR-19a) |
| Role detail | `/roles/[role_id]` | match summary, career-stage badge, gaps + next steps, role description, required skill list (with any-of groups), nice-to-have and soft skills, learning path, salary ranges and market demand (labelled "ข้อมูลกรุงเทพฯ"), listings, freshness badge, disclaimers; a "เกี่ยวกับข้อมูลสายงานนี้" block shows `author`, `reviewer`, `sources`, and for `status: "draft"` the label "ร่าง ยังไม่ได้ตรวจทาน" |
| Account | `/account` | email, quota today, removed skills (restore), delete all data |
| Admin | `/admin` | admins only (`User.is_admin`, FR-40); full width (no 1120 px cap); on screens at least 1280 × 800 the whole dashboard fits the window with no page scrolling: a 6 × 3 grid sized to the space under the header and scaled to the window height (zoom, designed for 1080 px, not below 0.8; a tile that still does not fit scrolls inside); the warning list is a "คำเตือน N" button with a dropdown and the cache table opens in a dialog from the cache map; smaller screens keep the scrolling layout. Bento grid: header with health chips (API, database, last request), the window switch (วันนี้ / 7 วัน / 30 วัน), last updated time and refresh; warning list; then tiles (4 columns at `lg`, 2 at `md`, 1 below): KPIs คำขอทั้งหมด / อัตราข้อผิดพลาด / ความหน่วง AI (big number + status pill with icon), a tall cache freshness map (one cell per role, one-hue teal by age; stale, failed and empty cells add texture and an icon; hover/focus reads a cell; status strip, Apify budget meter, note), the sign-up funnel (step columns with the share kept between steps), AI usage per model (10-segment meters for tokens and requests, amber past the warning line), a highlight card (overall conversion and the biggest drop), AI Router (sorted route list with leader lines, decision-layer strip, rates), average completeness gauge with the 65% threshold, user quota, errors by code (priority codes first), inputs and chat edits (strips), removed skills, and the sortable cache table. Notes under charts are computed from the numbers on the page and say so; they are not AI predictions. No pie or donut charts; parts of a whole use stacked strips in the validated series colours (`--color-series-1..3`); non-admins who open the URL see a 403 page "หน้านี้สำหรับผู้ดูแลระบบเท่านั้น" |

The chat stays available on Profile and Role pages behind a round button at the bottom right that shows the user's own work-style character, so the user can edit by chat at any time (PRD §5 step 7). The button opens a 400 × 600 popover (non-modal, can be widened) from `sm` up, and a full-height sheet on phones (modal; Escape, the backdrop or a swipe down closes it). A reply that arrives while the chat is closed shows as a count on the button; open or closed is remembered per browser. Page content uses the full width.

### 4.1 Site map

Navigation view of the page table above. `[Page]` is a screen with its own route, `[Menu]` is a header menu, and `[Action]` is a button that moves the user to another area. Items without a tag are sections inside their parent page. Requirement IDs refer to [PRD.md](PRD.md).

```
CareerMirror
│
├── Landing / หน้าแรก [Page] /
│   ├── What the app does (self-understanding first), how it works in 4 steps
│   ├── Privacy summary
│   ├── สมัครใช้งาน [Action] → Register
│   └── เข้าสู่ระบบ [Action] → Login
│
├── Register / สมัครใช้งาน [Page] /register
│   ├── Email, password, display name
│   └── Consent notice (checkbox required, FR-26)
│
├── Login / เข้าสู่ระบบ [Page] /login (after login, opens the furthest unlocked step)
│
└── Main workspace (after login; step indicator 1 → 4)
    │
    ├── 1 ข้อมูลของคุณ / Intake [Page] /start (tabs in any order; CV or questionnaire needed before generating, FR-5a)
    │   ├── CV tab: upload PDF, review and correct extracted information (FR-3)
    │   ├── แบบสอบถาม tab (auto-saved): skills, work-style preferences (self-reported), motivation
    │   ├── แชท tab: follow-up questions to fill gaps (FR-8)
    │   └── Progress sidebar: completeness meter, สร้างโปรไฟล์ [Action] (enabled when can_generate; unlocks 2 and 3)
    │
    ├── 2 โปรไฟล์ / Profile [Page] /profile (locked until a profile is generated)
    │   ├── Hard and soft skills (each skill chip has a remove button, FR-29)
    │   ├── Work-style preferences (self-reported, with disclaimer, FR-17)
    │   ├── Experience summary
    │   ├── Blind spots
    │   └── ดูสายงานที่เหมาะ [Action] → Role results
    │
    ├── 3 สายงานที่เหมาะ / Role results [Page] /roles (locked until a profile is generated)
    │   ├── Role match cards (top 5), or the closest roles with a below-threshold banner (FR-19a)
    │   └── ดูรายละเอียด [Action] → Role detail
    │
    ├── 4 รายละเอียดสายงาน / Role detail [Page] /roles/[role_id]
    │   ├── Match summary, gaps and prioritised next steps (FR-20a)
    │   ├── Role description
    │   ├── Salary ranges (Bangkok), market demand, listings (FR-21, FR-22, FR-22f)
    │   └── Data freshness badge and disclaimers (FR-22d)
    │
    ├── Chat (on Profile and Role pages: avatar button → popover, full-height sheet on phones)
    │   └── Edit by chat: each proposed change is confirmed or cancelled (FR-27)
    │
    └── Account / บัญชี [Menu] → [Page] /account
        ├── ธีม: สว่าง / มืด / ตามระบบ, shows the current choice (in the menu itself, FR-36)
        ├── แดชบอร์ดผู้ดูแล [Action] → Admin [Page] /admin (shown only when User.is_admin, FR-40)
        ├── Email, quota today and reset time (FR-25)
        ├── Removed skills (restore)
        └── Delete all data [Action] (confirm dialog, then back to Landing)
```

Rules that apply across the map:

- Evidence is shown inline on every claim in Profile, Role results and Role detail, never as a separate section (FR-16). Items the user changed are labelled "แก้ไขโดยคุณ" (FR-33).
- Removing a skill makes no LLM call and still works when the quota is used up. Edit by chat counts toward the quota (FR-30, FR-34).
- The theme toggle (สว่าง / มืด / ตามระบบ) is in the top bar of every page, including Landing, Register and Login; after login the account menu also shows the current theme (FR-36, FR-37).
- Every salary figure shows its source, measure and date (FR-21) and is labelled as Bangkok data (FR-22f). Salary, market and listings show the "last updated" date (FR-22d).
- Locked steps still appear in the step indicator, disabled, with a Thai hint saying what unlocks them.
- The admin page has no step indicator and no chat panel. It shows aggregates only, never user content or emails (FR-42).

## 5. Content rules (Thai)

- Tone: polite and friendly, address the user as "คุณ"; no slang; short sentences. Exact tone examples come from CIBrand.md section 5.
- **Numbers**: thousands separator, THB with "฿" before the number: "฿45,000". Ranges with an en dash and spaces: "฿35,000 – ฿55,000". Always add the measure: "/ เดือน (ฐานเงินเดือน)" or "/ ปี (รวมทุกอย่าง)".
- **Percent**: integer with "%": "72%". Never decimals for match %.
- **Dates**: Thai short format with Buddhist year, "3 พ.ย. 2569" (assumed); time "14:05 น.". API stays ISO 8601.
- **Skill names**: Thai name with the English name when it is a technology: "ภาษา Python", "Docker". Keep the official English spelling of tools.
- **Required disclaimers** (exact text to be agreed):
  - Work-style: "ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ" (FR-17).
  - Market data: "ข้อมูลประกาศงานรวบรวมจากแหล่งที่ไม่เป็นทางการ อาจไม่ครบถ้วน" (PRD §7 Data terms).
  - Role profiles and reference table: "จัดทำโดยทีมผู้พัฒนา" with sources.
  - Questionnaire page footer: "คำถามพัฒนาโดยทีมผู้พัฒนา โดยดัดแปลงจากมิติ Work Styles และ Skills ของ O\*NET® (USDOL/ETA, CC BY 4.0) ซึ่ง USDOL/ETA ไม่ได้รับรองเนื้อหานี้" with links to the source and the licence. A "แหล่งอ้างอิง" link shows the full English attribution from `data/questionnaire.json` (`sources[].attribution`).
  - Match %: "คำนวณจากทักษะที่ตรงกับสายงาน ไม่ใช่การรับประกันการได้งาน".
- **Error messages**: say what happened and what to do next, in one or two sentences: "ไฟล์นี้ไม่ใช่ PDF กรุณาอัปโหลดไฟล์ .pdf ขนาดไม่เกิน 5 MB". Never show stack traces or English error codes as the main text.
- **AI wording**: say "AI" for the product's assistant features (e.g. "แชทกับ AI"); do not name model vendors in the UI.

## 6. Accessibility

- Contrast: WCAG 2.1 AA — 4.5:1 for body text, 3:1 for large text and UI borders. Check every CIBrand pair before use, in both the light and the dark theme.
- Minimum body font size 16 px; never below 12 px.
- Full keyboard use: visible focus ring (2 px, `--color-primary`, 2 px offset), logical tab order, Esc closes popovers and dialogs.
- Every input has a `<label>`; errors linked with `aria-describedby`; the completeness meter uses `role="progressbar"` with `aria-valuenow`.
- Chat log uses `aria-live="polite"` for new assistant messages; loading states announce "กำลังโหลด".
- Hit targets at least 44 × 44 px on touch (skill chip remove button included).
- Page `lang="th"`.
- Themes: respect `prefers-color-scheme` by default; the user's choice overrides it (FR-36).
- Status never shown by colour alone (icons + text for matched/missing, fresh/stale).
