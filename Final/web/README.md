# CareerMirror web

Next.js (App Router) in JavaScript, Tailwind CSS 4, Thai UI. UI rules: [docs/DesignSystem.md](../docs/DesignSystem.md) · brand values: [docs/CIBrand.md](../docs/CIBrand.md) · brand book: [docs/brand/](../docs/brand/) · API: [docs/Contract.md](../docs/Contract.md).

## Run locally

```bash
cd web
npm install
npm run dev          # http://localhost:3000
npm run lint
npm run build
```

The browser calls `/api/*` on the web origin; `app/api/[...path]/route.js` forwards each request to the api. Outside Docker it uses `API_BASE_URL=http://localhost:8000` unless you set another value (for example in `web/.env.local`, which git ignores). Start the api first (see `api/README.md`).

With Docker, `docker compose up --build` from the repo root starts `web` on port 3000 next to `api` and `db`.

## Mock data

Pages call the api only through `lib/data.js`. Each function there reads either the real api (through `/api`) or an in-browser mock (`lib/mock/server.js`) that returns the same Contract.md shapes and error codes, so pages work before an endpoint exists.

- **Default:** on for `npm run dev` (`NEXT_PUBLIC_MOCK_API=1` in `.env.development`), off for `npm run build` and Docker.
- **Switch in the browser:** the "ข้อมูลจำลอง" button at the bottom right (shown in dev, or whenever mock data is on), or open any page with `?mock=on` / `?mock=off`. The choice is kept in localStorage.
- **Mock state** (CV, answers) is kept in localStorage; "รีเซ็ตข้อมูลจำลอง" clears it.
- **CV scenarios:** any PDF gives a sample CV; a file name containing `scan` gives `CV_UNREADABLE`; a non-PDF or a file over 5 MB gives the file errors.
- **Chat scenarios:** "ช่วยถามสิ่งที่ยังขาดให้หน่อย" starts the gap questions; each answer fills that slot (skills are read from text such as "Python 3, SQL 2, Git 2"). Questions about skills or salary get cited answers; the message `quota` uses up today's quota (`QUOTA_EXCEEDED`).
- **Profile:** "สร้างโปรไฟล์" builds it from the CV, answers and chat facts (`lib/mock/profile.js`); removed skills stay out when it is rebuilt.
- **Chat edits** (after a profile exists): "เปลี่ยนระดับ SQL เป็น 3", "เพิ่ม Docker ระดับ 2", "ลบ React", "เงินเดือนที่อยากได้ 40000" give an edit proposal card (expires after 15 min). Asking to add a removed skill shows "เพิ่มทักษะที่คุณเคยลบกลับมา".
- **Roles:** matches use the Design.md 4.3 formula on the role files in `/data` (`lib/mock/roles.js`); after any edit, reasons are stale until "อัปเดตคำอธิบาย". Remove a key skill to see the below-threshold banner. Market: `devops-engineer` is refreshing (no cache, appears after ~12 s of polling), `cloud-engineer` is stale; listings and advertised ranges are invented.
- **Delete account** (`/account`) clears the mock state.
- **Admin** (`/admin`): the mock user is an admin; switch "บัญชีผู้ดูแล" off in the mock toolbar to see the 403 page. The overview has two models above 80% of today's limit, one stale role cache, one with an error and one refreshing.
- **Admin warning colours** use `NEXT_PUBLIC_ADMIN_WARN_LLM_PCT` (80) and `NEXT_PUBLIC_ADMIN_WARN_ERROR_PCT` (5), read at build time; keep them equal to the api's `ADMIN_WARN_*`. The warning list itself comes from the api.
- **Questions and roles come from `/data`:** after changing `data/questionnaire.json`, `skills.json`, `roles.json`, `roles/*` or `salary/reference.csv`, run `npm run mock:fixtures` and commit `lib/mock/fixtures/`.

## Layout

```
app/
  layout.js             fonts (Anuphan + Urbanist), lang="th", theme provider, top bar
  globals.css           design tokens: light values in @theme, dark values in .dark
  page.js               landing page
  start/page.js         step 1: intake (tabs CV / แบบสอบถาม / แชท + completeness sidebar)
  profile/page.js       step 2: profile (skill chips, citations, work style, blind spots, chat panel)
  roles/page.js         step 3: role results (top 5 match cards, below-threshold banner, stale explanations)
  roles/[role_id]/      step 4: role detail (match, radar, gaps, required skills, salary, market, listings)
  account/page.js       account: email, quota, removed skills, delete all data
  admin/page.js         admin dashboard: warnings, health, AI usage, quota, cache table, router, funnel
  icon.svg              favicon from the logo mark
  api/[...path]/route.js  /api proxy to the api container
components/
  theme-provider.js     next-themes: light / dark / system, saved in localStorage
  theme-toggle.js       icon button + menu: สว่าง / มืด / ตามระบบ
  top-bar.js            app-shell top bar (app name, theme toggle; account slot after login)
components/app/          account-slot (quota + account menu), step-indicator, mock-toolbar,
                         citation ([n] evidence popover), confirm-dialog
components/intake/       intake page: tabs, CV upload and review, questionnaire items, completeness panel
components/chat/         chat panel (history, citations, quota state), edit proposal card, WithChat layout
components/roles/        role match card, role results, role detail, market (salary, demand, listings, freshness)
components/account/      account page and the type-DELETE dialog
components/admin/        admin dashboard panels (aggregates only, refreshes every 60 s)
components/profile/      profile page and skill chip (level dots, remove, "แก้ไขโดยคุณ")
  logo.js               logo mark and wordmark, coloured by tokens
components/charts/       chart card + table view, meter, skill radar, match, salary range,
                         work style, admin charts (Recharts 3; examples at /examples/charts)
lib/
  api.js                fetch helper: JSON or FormData body, ApiError with message_th, quota headers
  data.js               every api call the pages make; picks the real api or the mock
  session.js            shared user + quota for logged-in pages; 401 → /login?next=…
  config.js             APP_NAME (build time) and API_BASE_URL (request time)
  format.js             ฿, %, numbers and Thai dates (DesignSystem.md 5)
  use-motion.js         reduced-motion check, count-up and grow-in helpers
  mock/charts.js        mock data for /examples/charts only
  mock/mode.js          mock on/off switch (env default, localStorage, ?mock=)
  mock/server.js        in-browser mock api (auth, quota, CV, questionnaire, completeness, chat, profile, edits, roles, market)
  mock/profile.js       builds the mock Profile with evidence from CV, answers and chat facts
  mock/roles.js         mock matching (Design.md 4.3), role detail and market data
  mock/admin.js         mock AdminOverview with built-in warning states
  mock/fixtures/        generated from /data by scripts/build-mock-fixtures.mjs
```

## Rules

- Colours, fonts, radius and type sizes come only from the tokens in `app/globals.css`, which mirror CIBrand.md. The default Tailwind colour palette is switched off, so only brand utilities exist: `bg-bg`, `bg-surface`, `border-border`, `text-text`, `text-text-muted`, `bg-primary`, `text-on-primary`, `bg-primary-subtle`, `text-accent`, `text-success`, `text-warning`, `text-danger`, `text-info`. Charts use `--color-chart-you` and `--color-chart-ref` (DesignSystem.md 1.5).
- Never use hex values or `dark:` colour overrides in components; every token already has a dark value.
- Type sizes: `text-display`, `text-h1`, `text-h2`, `text-h3`, `text-body`, `text-small`, `text-tiny` (sizes and line heights from DesignSystem.md 1.2). Radius: `rounded-sm` 8 px, `rounded-md` 12 px, `rounded-lg` 16 px, `rounded-xl` 20 px.
- Frosted glass (`glass`) and the brand gradient (`bg-brand-gradient`) only on the hero and empty states.
- All user-facing text is Thai; call the API with `api()` from `lib/api.js` and show `error.messageTh` on failure.
- If the proxy cannot reach the api it returns `502` with code `INTERNAL_ERROR` and a Thai message.
