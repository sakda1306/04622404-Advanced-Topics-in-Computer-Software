# CareerMirror: Work-style avatar (proposal)

<!--
PURPOSE: Idea and plan for a character that mirrors the user's own work-style answers.
STATUS: revised proposal, 2 Nov 2026. The mapping in section 4 follows the design study in
design/AvatarStudio.html (one part per trait, five fixed variants each). Integration into the
other project specifications is pending agreement by both members (section 8).
DOES NOT CONTAIN: final colour tokens (see CIBrand.md), endpoint shapes (see Contract.md).
OWNER: Automatic28m (web). Drafted 2 Nov 2026.
-->

Requirements: [PRD.md](PRD.md) · UI rules: [DesignSystem.md](DesignSystem.md) · Colours: [CIBrand.md](CIBrand.md) · Data: [Contract.md](Contract.md) · Design study: [design/AvatarStudio.html](../design/AvatarStudio.html)

## 1. Idea

Each user gets a small illustrated character that mirrors **their own work-style answers**. The look follows flat, hand-drawn mascot characters: a rounded body with a dark outline, a simple face, hair, arms and two standing legs, on a pale background circle.

The character is not chosen from a fixed set. It is **assembled from parts**: each of the six work-style questions controls one part, and each answer (1 to 5) selects one of five variants of that part. Two users with different answers get different characters; a user who changes an answer sees that one part change.

The name of the product is CareerMirror; the avatar is the most literal form of that mirror.

## 2. Why parts, not types

| Option | Problem |
|---|---|
| Four or five fixed characters ("the Calm one", "the Curious one"), one assigned per user | This is a personality type. PRD FR-7 rules out MBTI or personality-type diagnosis, and FR-17 says work style is a self-reported preference, not a diagnosis or fact. A type label also hides which answers led to it. |
| One character per role (26 roles) | Too many to design and tell apart, and it mirrors the role catalogue, not the user. |
| **Character assembled from the six answers (chosen)** | 5^6 = 15,625 combinations, no types and no labels. Every part traces back to one answer, so it can be explained and cited (FR-16). It stays a preference picture, in line with FR-17. |

Rules that keep it on the right side of FR-7 and FR-17:

- No type names, no captions such as "You are curious". The caption is always "ตัวละครจากความชอบในการทำงานของคุณ". Variant names (section 4) are for the design team and the explanation list, never a title for the user.
- The required disclaimer stays next to it: "ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ" (DesignSystem.md section 5).
- No answer is "better". All five variants of every part must look equally friendly and equally finished.
- **Faces (changed 2 Nov 2026).** The first draft kept one neutral face for everyone, because an expression can read as a judgement of the person. The face now follows `ambiguity`, as requested. To keep it a preference picture: all five faces are positive or neutral (no sad, worried, angry or tired face); the explanation describes the face as how the character meets an open problem ("ยิ้มสงบ · เพราะคุณอยากได้โจทย์ชัดก่อนเริ่ม"), never as the user's mood or personality; and the face is never shown without the explanation list or the disclaimer. Both members should confirm this change (section 9).

## 3. Data source

No new data is needed. The avatar reads `Profile.preferences.work_style` (Contract.md section 3): one value from 0 to 1 per trait, computed as `(answer − 1) / 4` from the six `ws_*` questions in `data/questionnaire.json` (Design.md section 6). The same values can come from chat (FR-8) or a confirmed chat edit (FR-27); the avatar does not care where they came from.

Before a profile exists (intake page), the web can compute the same values from the saved answers (`GET /api/questionnaire/answers`), so the character can grow while the user answers.

The variant is `step = round(value × 4) + 1`, so answers 1 to 5 map to variants 1 to 5. A chat edit that stores a value between steps (for example 0.6) uses the nearest variant.

| trait | question | 1 means | 5 means |
|---|---|---|---|
| `teamwork` | `ws_teamwork` | ทำงานคนเดียวเป็นหลัก | ทำงานร่วมกับทีมตลอด |
| `structure` | `ws_structure` | ชอบคิดวิธีทำเองอย่างยืดหยุ่น | ชอบมีขั้นตอนและมาตรฐานชัดเจน |
| `ambiguity` | `ws_ambiguity` | อยากได้โจทย์ชัดก่อนเริ่ม | สนุกกับการค้นหาคำตอบเอง |
| `pressure` | `ws_pressure` | จังหวะสม่ำเสมอ วางแผนล่วงหน้าได้ | งานเร่งด่วน เดดไลน์กระชั้น |
| `innovation` | `ws_innovation` | ใช้วิธีที่พิสูจน์แล้วว่าได้ผล | ลองวิธีหรือเครื่องมือใหม่ ๆ |
| `leadership` | `ws_leadership` | รับผิดชอบงานส่วนของตัวเอง | นำทีมและประสานงานกับคนอื่น |

## 4. Trait-to-part mapping

One part per trait, five clearly different variants per part. Every variant keeps the same outline, the same legs and the same size, so a change in one answer changes one part only.

| trait | part | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| `teamwork` | body shape | circle | squircle | rounded rectangle | rounded rectangle with a puffy top | cloud |
| `structure` | hair | wild swirl | messy tuft | single curl | side-swept fringe | neat bowl cut |
| `ambiguity` | face | calm (dot eyes, small even smile) | happy (dot eyes, open smile) | curious (raised brow, smirk) | surprised (tall eyes, round open mouth) | goofy (wink, grin with a tooth) |
| `pressure` | colour | blue | green | yellow | orange | coral |
| `innovation` | idea doodle beside the head (**proposed, not in the brief**) | open book | gear | light bulb | paper plane | sparkles |
| `leadership` | arms and hands | arms at sides | hands together | open-hand gesture | pointing the way (other hand on hip) | both arms up, rallying |

Fixed for everyone: the legs (one standing pose), the outline, the body size and position, and the pale background circle.

Notes per part:

- **Body (`teamwork`).** From one closed shape to a cluster of bumps: working alone to working with a team. The cloud and the puffy top are unions of circles and a rounded rectangle under one outline. Teamwork no longer changes colour.
- **Hair (`structure`).** From loose, free lines to tidy, even shapes: own flexible approach to clear steps and standards. Variants 1 to 3 are ink lines above the head; variants 4 and 5 are filled ink shapes clipped to the body outline.
- **Face (`ambiguity`).** Faces follow the reference sheet. From a settled face (wants a clear brief) to a playful, exploring face (enjoys open problems). See the face rule in section 2.
- **Colour (`pressure`).** See section 6.
- **Idea doodle (`innovation`).** The brief maps five traits; innovation had no part. The doodle is a proposal so that all six answers stay visible: from a solid, known object (proven methods) to a new, light one (new methods or tools): open book (follow the tried recipe), gear (tune what works), light bulb (a new idea), paper plane (try it out), sparkles (something new). It can be switched off in the design study. Open question 1.
- **Arms (`leadership`).** From keeping to one's own part (arms at sides) to leading and coordinating (pointing the way, rallying). Arms start at the lower sides of the body and never cross the face.

### Missing answers

- Keep missing values as `null` or absent. Never save a visual fallback as an actual answer of 3/5.
- If any of the six answers is missing, draw the body outline dotted (round caps, even spacing) and show "ยังตอบไม่ครบ · X/6 ข้อ". The body stays filled; the dotted line is a status cue, not a score.
- A missing part uses a neutral stand-in: body = rounded rectangle (variant 3); hair = none; face = calm (variant 1); colour = neutral grey (`avatar.pending`); doodle = none; arms = arms at sides (variant 1). The explanation list says "ยังไม่มีคำตอบ" for that part and has no citation.
- With no answers at all, show the neutral stand-in with the prompt "ตอบ 6 ข้อนี้เพื่อสร้างตัวละครของคุณ" and a link to the questionnaire tab.
- The design study does not show missing states yet (plan step 5).

## 5. Explaining the character

The avatar must explain itself, the same way every profile claim cites its evidence (FR-16).

- Next to the avatar, one line per part names the variant and the answer behind it, for example "ตัวกลม · เพราะคุณตอบว่าชอบทำงานคนเดียวเป็นหลัก [4]" or "สีฟ้า · เพราะคุณชอบจังหวะสม่ำเสมอ วางแผนล่วงหน้าได้ [7]". The colour line shows a swatch. Missing answers say "ยังไม่มีคำตอบ".
- `[n]` reuses the existing citation popover (`components/app/citation.js`) and points to the questionnaire answer, the chat message, or "คุณแก้ไขเอง" for a confirmed edit (FR-33).
- Hovering or focusing a line highlights that part of the drawing.
- Citations need evidence ids per trait. `Profile.work_style.traits` does not carry them in Contract.md v0.3; the web mock already sends an optional `evidence_ids` per trait. This is the only contract change the avatar would need (section 8).

## 6. Visual style and colour

### Art direction

Flat fills, no gradients, shadows or highlights. One dark ink colour for the outline, face, hair lines and doodle. Arms and legs use a darker shade of the body colour, as in the reference sheet. The background circle is a pale tint of the body colour.

### Pressure colours

Colour follows the pace the user prefers, from calm and cool to energetic and warm. The meanings are this product's legend, not universal colour meanings. No colour says anything about ability, mood, seniority or personality, and the page states this next to the legend.

| answer | colour | meaning in the legend | body | arms and legs | circle |
|---|---|---|---|---|---|
| 1 | blue | calm, steady, a planned rhythm | `#3C8DF5` | `#1F6FD8` | `#DCEAFB` |
| 2 | green | balanced, a sustainable pace | `#2DC796` | `#13A37A` | `#D5F2E7` |
| 3 | yellow | alert, ready to switch gears | `#F7CB4D` | `#E5A936` | `#FBF0D3` |
| 4 | orange | energetic, quick to act | `#FF9F45` | `#E97D2A` | `#FDE5CF` |
| 5 | coral | high energy, enjoys a deadline rush | `#FF7470` | `#E1504F` | `#FDDFDD` |
| missing | neutral grey | not answered yet | to be chosen | to be chosen | to be chosen |

Coral is used for 5 instead of red, so the top answer does not read as an error or danger state. The values are the design study's; they become tokens `avatar.pressure.step1..step5.{body,shade,backdrop}`, `avatar.pending.*` and `avatar.ink` in CIBrand.md after review. They are an **avatar-only** palette and are not used elsewhere in the UI.

### Contrast (measured)

| check | result | rule |
|---|---|---|
| face ink `#1b1b1f` on each body colour | 5.2 (blue) to 11.1 (yellow) | at least 4.5:1, passes |
| ink on each arm and leg shade (finger lines) | 3.5 (blue) to 8.2 (yellow) | non-text, at least 3:1, passes |
| outline on each background circle | 13.7 to 15.1 | at least 3:1, passes |
| outline on the light page (`#FFFFFF`) | 17.2 | passes |
| outline on the dark page (`#0C1922`) | 1.04 | **fails** |

Rule from the last row: the pale background circle is **always drawn, in both themes**, and every part (raised hands, hair swirl, doodle) stays inside it, so the outline always sits on a light colour. Body colour against its circle is low (1.4 to 2.7) on purpose; the outline carries the silhouette.

### Rendering

1. Drawing box 240 × 260. Layer order: circle, legs, body, filled hair (variants 4 and 5), face, line hair (variants 1 to 3), arms and hands, doodle.
2. Outline: draw each part twice, first in ink 3 px wider on each side, then in its colour. Unions of shapes (cloud, puffy top, arm plus hand) get one clean outline this way.
3. Legs are fixed strokes with rounded feet; arms are strokes from the lower sides of the body to the hands.
4. Filled hair is clipped to the body shape so it follows every silhouette.
5. Output is a pure function of the six steps and the theme: no randomness. Every rendered instance uses unique clip ids.
6. Sizes: 120 to 200 px full figure. Below 48 px, crop to head and shoulders and drop the doodle and finger lines; the explanation list or the `aria-label` still carries every part.

## 7. Where it appears

| place | size | notes |
|---|---|---|
| Profile page, work-style card | 160 to 200 px | with the feature list and citations (section 5) and the disclaimer |
| Intake page, after the work-style questions | 120 px | grows live as the user answers; neutral stand-ins and a dotted outline for questions not answered yet |
| Account menu button in the top bar | 32 px | replaces the initial letter; head and shoulders only, no doodle (section 6) |
| Chat, beside the user's own messages | 28 px | optional; decide after the first version |

Not on the role pages: the match % does not come from this picture (the work-style part of the score is 5%, Design.md section 4.3), and showing it there would suggest it drives the result.

## 8. Changes to other docs

| doc | change | needs |
|---|---|---|
| PRD.md | under FR-17, one line: "A work-style avatar may illustrate the self-reported preferences. It is assembled from one part per answer, has no type names, keeps the disclaimer, and its face shows how the character meets an open problem, not a mood of the user." | both members |
| DesignSystem.md section 3 | new component row **Work-style avatar**: sizes, mapping table (or a link to this file), missing-answer state, explanation list, accessibility rules | both members |
| DesignSystem.md section 4 | Profile page row: add the avatar to the work-style section | both members |
| CIBrand.md section 3 | avatar-only palette: five pressure colours (body, shade, backdrop), pending grey, ink; the contrast table and the always-on circle rule from section 6 | both members |
| Contract.md | `Profile.work_style.traits[].evidence_ids: string[]` (optional), plus a change-log row | both members (sakda1306 implements it in the profile builder) |

## 9. Open questions

1. Innovation: keep the proposed idea doodle, choose another part, or leave innovation out of the picture (it would then appear only in the explanation list)?
2. Faces from `ambiguity` (section 2): both members confirm the change and the wording rule.
3. Should the user be able to adjust the drawing directly, or only through their answers? Recommendation: only through answers and chat edits, so the picture always matches the data.
4. Show it in chat (section 7), or keep chat clean?
5. Should the user be able to download or share the image? It shows nothing personal beyond preferences, but sharing would need a short notice. Recommendation: not in the first version.

## 10. Accessibility

- The SVG has `role="img"` and an `aria-label` built from the explanation list, for example "ตัวละครจากความชอบในการทำงานของคุณ: ตัวกลม ผมม้วนเส้นเดียว หน้ายิ้มสงบ สีฟ้า แขนแนบลำตัว".
- No meaning by colour alone: the colour line in the explanation list names the colour and the pressure answer in words. Completion status is text ("ยังตอบไม่ครบ · X/6 ข้อ"); a dotted outline is never described as a lower score.
- Changes animate for at most 300 ms and not at all with `prefers-reduced-motion`.
- The feature list is real text, keyboard focusable through its citations, and works in both themes.

## 11. Plan

| # | step | output | depends on |
|---|---|---|---|
| 1 | Agree on this proposal and the open questions (section 9) | decisions recorded here | team |
| 2 | Update PRD.md, DesignSystem.md (and CIBrand.md, Contract.md if needed) as in section 8 | doc PR | 1 |
| 3 | Design study of all parts: five variants each for body, hair, face, colour, doodle and arms; fixed legs; outline | `design/AvatarStudio.html` (done 2 Nov 2026) | – |
| 4 | Build `components/profile/work-style-avatar.js`: pure function of the six values, sizes 28 to 200 px, missing-answer state | component | 3 |
| 5 | Preview page `/examples/avatar`: the studio controls and variant sheet, plus missing-answer toggles per trait and the dotted states | page for tuning and review | 4 |
| 6 | Tune the parts by eye; repeat the contrast table in section 6 for the final tokens and the pending grey, in both themes | final rules in sections 4 and 6 | 5 |
| 7 | Add to the profile work-style card with the feature list and citations | profile page | 4, Contract change for citations |
| 8 | Add the live version to the intake page and the small version to the account menu | intake, top bar | 4 |
| 9 | Check every variant of every part, the missing states and all sizes in both themes with the FR-39 pass | checklist result | 7, 8 |

Out of scope for the first version: user-drawn changes, sharing or downloading, animation beyond short transitions, any link between the avatar and role matching.
