# CareerMirror: CI Brand

<!--
PURPOSE: Source of truth for brand identity: name, logo, colours, fonts, tone of voice.
DesignSystem.md takes its colours and fonts from here. Change values here only; never copy them into other files.
DOES NOT CONTAIN: component or layout rules (DesignSystem.md).
-->

Brand: **Mist Slate**, with a light and a dark theme (decided 1 Nov 2026). Full visual brand book: [docs/brand/CareerMirror_BrandBook_MistSlate.pdf](brand/CareerMirror_BrandBook_MistSlate.pdf).

## 1. Brand summary

- **Name**: CareerMirror (shown in the app from `APP_NAME`).
- **One line**: A calm mirror that helps Thai job seekers see their own strengths before they apply.
- **Thai**: แอปที่ช่วยให้คุณเห็นจุดแข็งและช่องว่างของตัวเอง ก่อนเลือกสายงาน IT ที่ใช่
- **Personality**: Calm, Clear, Reassuring.
- **Design idea**: job hunting is stressful, so the brand is quiet. Deep slate stands for trust, soft mint for growth, and frosted-glass surfaces keep the UI light. Colour is used sparingly so the user's own data (skills, match %, salary) stands out. The dark theme turns the slate into the canvas and the mint into the light.

## 2. Logo

- **Concept**: a circle split down the middle: a solid half and its translucent reflection (a mirror; "you now" next to "you next"). Wordmark: **Career** in Urbanist Bold + Mirror in Urbanist Regular.
- **Files** (to create): `web/public/brand/logo-light.svg` (slate, for the light theme), `logo-dark.svg` (mint and off-white, for the dark theme), `logo-mono.svg` (single colour, black or white), `mark.svg`, `favicon.ico`. The app swaps the light and dark files with the theme.
- **Minimum size**: full logo 120 px / 30 mm wide; mark alone 24 px.
- **Clear space**: half the mark's height on every side.
- **Do**: use the versions above; use mono black or white for print.
- **Don't**: stretch, rotate, recolour outside the palette, add shadows or glow, or place it on a busy image.

## 3. Colours

Every name has a light and a dark value. DesignSystem.md maps one token to each name; switching the theme swaps the value only. In the dark theme the neutral scale stays semantic: Neutral 0 is the page background (darkest) and Neutral 900 the body text (lightest).

| Name | Light | Dark | Use |
|---|---|---|---|
| Primary | `#1B405B` | `#9FD9C6` | main buttons, links, active tab, meter fill |
| Primary Dark | `#163144` | `#C4EADD` | hover / pressed (darker in light, lighter in dark) |
| Primary Light | `#DFF3EB` | `#1B405B` | selected chip, highlighted card background |
| On Primary | `#FFFFFF` | `#0C1922` | text and icons on Primary and Primary Dark |
| Accent | `#2C7A74` | `#6CC3B6` | match % emphasis, highlights (sparingly) |
| Neutral 0 | `#FFFFFF` | `#0C1922` | page background |
| Neutral 50 | `#F2F6F6` | `#13242F` | cards, sidebar |
| Neutral 200 | `#D3DEE1` | `#2A4250` | dividers, input borders |
| Neutral 600 | `#556A75` | `#93A8B2` | captions, sources, dates |
| Neutral 900 | `#122634` | `#E8F3EF` | body text |
| Success | `#2E7D5B` | `#5CCB98` | matched skills, saved state |
| Warning | `#9A5B00` | `#E9B44C` | missing skills, stale data, quota low |
| Danger | `#C0362C` | `#F2766C` | errors, destructive actions |
| Info | `#2F6690` | `#72B4E6` | notices, disclaimers |
| Chart You | `#0D9298` | `#0D9298` | the user's data in charts (radar fill, bars, main line) |
| Chart Reference | `#49585D` | `#A9B9BF` | the role's or a reference value in charts, always drawn dashed or as an outline |

Brand gradients (hero, cover and empty states only; never body text on their mid-tones):

- Light "Mist": `linear-gradient(180deg, #1B405B 0%, #7E9BA6 45%, #DFF3EB 85%, #F7FCFA 100%)`
- Dark "Night": `linear-gradient(180deg, #0C1922 0%, #163144 45%, #1B405B 75%, #3D6A74 100%)`

Contrast notes (WCAG 2.1 AA, ratio against Neutral 0 unless stated; all 14 checked pairs pass in both themes):

| Pair | Light | Dark |
|---|---|---|
| Neutral 900 (body text) | 15.5:1 | 15.7:1 |
| Neutral 600 (captions) | 5.7:1 | 7.2:1 |
| Primary (links) | 10.9:1 | 11.2:1 |
| On Primary on Primary / Primary Dark | 10.9:1 / 13.5:1 | 11.2:1 / 13.7:1 |
| Neutral 900 on Primary Light (chips) | 13.4:1 | 9.6:1 |
| Accent (large text only) | 5.1:1 | 8.6:1 |
| Success / Warning / Danger / Info text | 5.0 / 5.4 / 5.5 / 6.1:1 | 8.9 / 9.4 / 6.4 / 8.0:1 |

Never put white text on the dark-theme Primary (mint); use On Primary.

Chart colours: the Mist Slate colours are low-saturation, so as chart series they read as grey and fail colour-blind checks. Chart You and Chart Reference were chosen by a palette checker (OKLCH lightness band, chroma, colour-blind and normal-vision separation, 3:1 contrast). Results: separation ΔE 17.2 normal / 15.0 colour-blind in light, 19.3 / 14.6 in dark; both ≥ 3:1 against the page. Chart Reference is meant to read as grey and is always paired with a dashed line or outline, so colour is never the only difference.

## 4. Typography

- **Latin**: Urbanist (SIL OFL, Google Fonts): geometric, open shapes, light numerals.
- **Thai**: Anuphan (SIL OFL, Google Fonts): loopless modern Thai with the same round geometry.
- Load both with `next/font/google`, weights 400, 500, 600, 700. Stack: Thai font, then Latin font, then `system-ui, sans-serif`.
- Sizes and line heights are in DesignSystem.md section 1.2. Large numbers may use weight 300 in the light theme only; use 400 or heavier in the dark theme, because thin strokes blur on dark backgrounds.

## 5. Tone of voice (Thai)

Rules:

- สุภาพและเป็นกันเอง เรียกผู้ใช้ว่า "คุณ" ไม่ใช้คำแสลงหรือ 555
- ไม่ใส่คำลงท้าย ครับ/ค่ะ ในข้อความ UI เพื่อให้เป็นกลางทางเพศ
- ประโยคสั้น บอกสิ่งที่เกิดขึ้นและสิ่งที่ต้องทำต่อ ใน 1–2 ประโยค
- พูดถึงจุดที่ต้องพัฒนาอย่างสร้างสรรค์ ไม่ตัดสินตัวบุคคล
- ใช้คำว่า "AI" สำหรับผู้ช่วย ไม่ระบุชื่อผู้ให้บริการโมเดล
- ชื่อเทคโนโลยีใช้ตัวสะกดภาษาอังกฤษทางการ เช่น "ภาษา Python", "Docker"

Landing headline: "เข้าใจตัวเองก่อน แล้วงานที่ใช่จะชัดขึ้น"

| Case | Good | Bad |
|---|---|---|
| Error | ไฟล์นี้ไม่ใช่ PDF กรุณาอัปโหลดไฟล์ .pdf ขนาดไม่เกิน 5 MB | Error 415: CV_INVALID_TYPE |
| Empty state | ยังไม่มีโปรไฟล์ อัปโหลด CV หรือตอบแบบสอบถามเพื่อเริ่มต้น | ไม่มีข้อมูล |
| Gap | ทักษะที่ยังขาด: Docker เริ่มจากคอร์สพื้นฐานประมาณ 1–2 สัปดาห์ | คุณอ่อน Docker มาก |
| Match | ตรงกับสายงาน 72% คำนวณจากทักษะที่ตรงกับสายงาน ไม่ใช่การรับประกันการได้งาน | คุณได้งานนี้แน่นอน! |
| Quota | วันนี้ใช้ครบโควตาแล้ว ใช้งานได้อีกครั้งเวลา 00:00 น. | หมดโควตา ลองใหม่ |
| CTA | สร้างโปรไฟล์ | คลิกที่นี่ |
| Theme toggle | สว่าง · มืด · ตามระบบ | Light · Dark · Auto |

## 6. Imagery and icons

- **Surfaces**: frosted glass, only on brand-gradient areas (hero, cover, empty states). Light: white cards at 70–85% opacity, 1 px white edge, soft shadow. Dark: Neutral 50 cards at 75–85% opacity, 1 px mint (Primary) edge at 14% opacity, depth from lighter surfaces instead of shadows.
- **Gradients**: only on the hero, cover and empty states (section 3). Working screens use a flat Neutral 0 page with flat Neutral 50 cards and a 1 px Neutral 200 edge.
- **Shape**: soft, rounded corners: 8 px inputs, 12 px buttons, 16 px cards and dialogs, 20 px hero panels, full pills for skill chips. Token names are in DesignSystem.md section 1.3.
- **Charts**: thin Primary lines, hatched areas in Primary Light, no saturated colours; they follow the theme.
- **Icons**: Lucide (ISC licence), 1.5 px stroke, 20 px, Neutral 600, Primary when active. Theme toggle icons: sun, moon, monitor.
- **People**: no stock photos. Avatars are initials on Primary Light.
