// Work-style avatar (docs/WorkStyleAvatar.md, design/AvatarStudio.html).
// A character assembled from the six work-style answers: one part per trait,
// five variants per part. Pure functions only: the same answers always give the
// same drawing, and nothing here reads user text, so the markup is safe to inject.

/** Traits in answer order, with the Thai part and variant names for the explanation list. */
export const AVATAR_TRAITS = [
  {
    key: "teamwork",
    part_th: "รูปร่าง",
    ends_th: ["ทำงานคนเดียวเป็นหลัก", "ทำงานร่วมกับทีมตลอด"],
    names_th: ["ตัวกลม", "ตัวกลมมน", "ตัวเหลี่ยมมน", "ตัวหัวฟู", "ตัวก้อนเมฆ"],
  },
  {
    key: "structure",
    part_th: "ทรงผม",
    ends_th: ["คิดวิธีทำเองอย่างยืดหยุ่น", "มีขั้นตอนและมาตรฐานชัดเจน"],
    names_th: ["ผมขดอิสระ", "ผมกระเซิง", "ผมหยักเส้นเดียว", "ผมปัดข้าง", "ผมทรงกะลา"],
  },
  {
    key: "ambiguity",
    part_th: "ใบหน้า",
    ends_th: ["อยากได้โจทย์ชัดก่อนเริ่ม", "สนุกกับการค้นหาคำตอบเอง"],
    names_th: ["ยิ้มสงบ", "ยิ้มกว้าง", "ยิ้มสงสัย", "ตาโตตื่นเต้น", "ยิ้มขยิบตา"],
  },
  {
    key: "pressure",
    part_th: "สี",
    ends_th: ["จังหวะสม่ำเสมอ วางแผนได้", "งานเร่งด่วน เดดไลน์กระชั้น"],
    names_th: ["สีฟ้า", "สีเขียว", "สีเหลือง", "สีส้ม", "สีปะการัง"],
  },
  {
    key: "innovation",
    part_th: "ของข้างตัว",
    ends_th: ["ใช้วิธีที่พิสูจน์แล้ว", "ลองวิธีหรือเครื่องมือใหม่ ๆ"],
    names_th: ["หนังสือเปิด", "เฟือง", "หลอดไฟ", "เครื่องบินกระดาษ", "ประกายดาว"],
  },
  {
    key: "leadership",
    part_th: "ท่าแขน",
    ends_th: ["รับผิดชอบงานส่วนของตัวเอง", "นำทีมและประสานงาน"],
    names_th: ["แขนแนบตัว", "ประสานมือ", "ผายมือ", "ชี้ทาง", "ชูแขนสองข้าง"],
  },
];

// Pressure colour, calm and cool (1) to warm and energetic (5). light → main → shade
// is the body gradient; shade is also the arms and legs; back is the circle.
// `pending` is the neutral stand-in while the pressure answer is missing.
export const AVATAR_COLOURS = [
  { light: "#8CC0FB", main: "#3C8DF5", shade: "#1F6FD8", back: "#DCEAFB" },
  { light: "#7FE3C1", main: "#2DC796", shade: "#13A37A", back: "#D5F2E7" },
  { light: "#FCE596", main: "#F7CB4D", shade: "#E5A936", back: "#FBF0D3" },
  { light: "#FFC68E", main: "#FF9F45", shade: "#E97D2A", back: "#FDE5CF" },
  { light: "#FFABA8", main: "#FF7470", shade: "#E1504F", back: "#FDDFDD" },
];
const PENDING = { light: "#E6EBEE", main: "#C9D3D8", shade: "#9DABB3", back: "#EEF2F4" };

/** CSS gradient of a colour, for swatches. */
export const avatarSwatch = (step) => {
  const c = AVATAR_COLOURS[step - 1] ?? PENDING;
  return `linear-gradient(180deg, ${c.light} 0%, ${c.main} 50%, ${c.shade} 100%)`;
};

/** 1..5 from a stored 0..1 value (Profile.preferences.work_style), or null when missing. */
export function stepFromValue(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return Math.min(5, Math.max(1, Math.round(value * 4) + 1));
}

/** 1..5 from a questionnaire answer (already 1..5), or null when missing. */
export function stepFromAnswer(answer) {
  const n = Number(answer);
  return answer === null || answer === undefined || answer === "" || !Number.isInteger(n) || n < 1 || n > 5 ? null : n;
}

/** {teamwork: 1..5 | null, ...} from Profile.preferences.work_style. */
export const stepsFromWorkStyle = (ws) =>
  Object.fromEntries(AVATAR_TRAITS.map((t) => [t.key, stepFromValue(ws?.[t.key])]));

/** {teamwork: 1..5 | null, ...} from questionnaire answers keyed by question id (ws_teamwork, ...). */
export const stepsFromAnswers = (answers) =>
  Object.fromEntries(AVATAR_TRAITS.map((t) => [t.key, stepFromAnswer(answers?.[`ws_${t.key}`])]));

export const answeredCount = (steps) => AVATAR_TRAITS.filter((t) => steps[t.key] != null).length;

/** "เพราะคุณ…" reason for one part, from its step. */
export function reasonTh(trait, step) {
  if (step == null) return "ยังไม่มีคำตอบ";
  const [low, high] = trait.ends_th;
  if (step <= 2) return `เพราะคุณชอบ${low}`;
  if (step >= 4) return `เพราะคุณชอบ${high}`;
  return `เพราะคุณอยู่ระหว่าง “${low}” กับ “${high}”`;
}

/* ---------------- geometry (240 × 260 drawing) ---------------- */

const INK = "#1b1b1f";
const OUT = 3;

function superellipse(cx, cy, a, b, n, steps = 72) {
  let d = "";
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2;
    const c = Math.cos(t);
    const s = Math.sin(t);
    const x = cx + a * Math.sign(c) * Math.pow(Math.abs(c), 2 / n);
    const y = cy + b * Math.sign(s) * Math.pow(Math.abs(s), 2 / n);
    d += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
  }
  return d + "Z";
}

const BODIES = [
  { top: 52, parts: [["circle", 120, 116, 63]] },
  { top: 51, parts: [["path", superellipse(120, 115, 61, 64, 3.2)]] },
  { top: 50, parts: [["rect", 58, 50, 124, 130, 30]] },
  { top: 34, parts: [["rect", 60, 64, 120, 116, 28], ["circle", 86, 72, 24], ["circle", 120, 60, 27], ["circle", 155, 72, 24]] },
  {
    top: 36,
    parts: [
      ["circle", 120, 64, 29], ["circle", 85, 80, 27], ["circle", 155, 80, 27], ["circle", 66, 118, 27],
      ["circle", 174, 118, 27], ["circle", 88, 152, 29], ["circle", 152, 152, 29], ["circle", 120, 114, 50],
    ],
  },
];
const BODY_BOTTOM = 180; // every body ends at about y = 180, where the legs start

function shapes(parts, attrs) {
  return parts
    .map((p) => {
      if (p[0] === "circle") return `<circle cx="${p[1]}" cy="${p[2]}" r="${p[3]}" ${attrs}/>`;
      if (p[0] === "rect") return `<rect x="${p[1]}" y="${p[2]}" width="${p[3]}" height="${p[4]}" rx="${p[5]}" ${attrs}/>`;
      return `<path d="${p[1]}" ${attrs}/>`;
    })
    .join("");
}

const LEGS = ["M104 166 L101 226 L88 229", "M136 166 L140 226 L153 229"];

const ARMS = [
  [["M70 142 Q55 160 57 186", "down"], ["M170 142 Q185 160 183 186", "down"]],
  [["M72 148 Q72 178 112 179", "clasp"], ["M168 148 Q168 178 128 179", "clasp"]],
  [["M70 142 Q55 160 57 186", "down"], ["M170 140 Q208 138 208 104", "open"]],
  [["M70 142 Q44 156 66 172", "hip"], ["M170 138 Q202 118 220 90", "point"]],
  [["M70 138 Q44 116 38 80", "up"], ["M170 138 Q196 116 202 80", "up"]],
];

function lastPoint(d) {
  const nums = d.match(/-?\d+(\.\d+)?/g).map(Number);
  return [nums[nums.length - 2], nums[nums.length - 1]];
}

function hand(d, kind, shade) {
  const [x, y] = lastPoint(d);
  const extras = {
    down: `<path d="M${x - 4} ${y + 6} l-1 5 M${x + 1} ${y + 8} l0 5 M${x + 6} ${y + 6} l1 5"/>`,
    up: `<path d="M${x - 6} ${y - 5} l-3 -5 M${x} ${y - 8} l0 -6 M${x + 6} ${y - 5} l3 -5"/>`,
    open: `<path d="M${x - 6} ${y - 6} l-3 -6 M${x - 1} ${y - 9} l-1 -7 M${x + 5} ${y - 7} l2 -6 M${x + 9} ${y - 2} l5 -3"/>`,
    point: `<path d="M${x + 6} ${y - 6} l12 -12" stroke-width="7"/><path d="M${x + 6} ${y - 6} l12 -12" stroke="${shade}" stroke-width="2.5"/>`,
    hip: `<path d="M${x + 2} ${y - 7} l5 -3 M${x + 5} ${y - 1} l6 -1"/>`,
    clasp: "",
  };
  return { x, y, r: 9, extra: extras[kind] };
}

// Faces: `eyes` blink, `rest` (brows, mouth, the closed eye of the wink) does not.
const FACES = [
  {
    eyes: `<ellipse cx="109" cy="99" rx="2.8" ry="4.2"/><ellipse cx="131" cy="99" rx="2.8" ry="4.2"/>`,
    rest: `<path d="M105 113 Q119 118 135 111" fill="none" stroke-width="3.2"/>`,
  },
  {
    eyes: `<ellipse cx="108" cy="97" rx="3" ry="4.5"/><ellipse cx="131" cy="97" rx="3" ry="4.5"/>`,
    rest: `<path d="M104 107 Q119 110 135 105 Q133 124 119 124 Q106 123 104 107 Z"/><path d="M111 119 Q119 114 127 119 Q120 123 111 119 Z" fill="#fff"/>`,
  },
  {
    eyes: `<ellipse cx="109" cy="100" rx="2.8" ry="4.2"/><ellipse cx="131" cy="99" rx="3" ry="4.6"/>`,
    rest: `<path d="M102 90 L114 91" fill="none" stroke-width="3"/><path d="M124 87 Q131 79 139 85" fill="none" stroke-width="3"/><path d="M111 114 Q121 118 130 110" fill="none" stroke-width="3.2"/>`,
  },
  {
    eyes: `<path d="M112 89 l0 11 M126 89 l0 11" fill="none" stroke-width="3.4"/>`,
    rest: `<ellipse cx="119" cy="114" rx="5" ry="7"/><ellipse cx="119" cy="117" rx="2" ry="2" fill="#fff"/>`,
  },
  {
    eyes: `<ellipse cx="108" cy="98" rx="3" ry="4.5"/>`,
    rest: `<path d="M126 95 L134 99 L126 103" fill="none" stroke-width="3.2"/><path d="M98 107 Q119 120 141 104" fill="none" stroke-width="3.4"/><path d="M116 112 L116 121 Q120 124 125 121 L125 112" fill="#fff" stroke-width="2.6"/>`,
  },
];

function hair(i, top, clipId) {
  const t = `transform="translate(120 ${top})"`;
  const line = `fill="none" stroke="${INK}" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"`;
  switch (i) {
    case 0:
      return `<path ${t} ${line} d="M-4 2 C -6 -26, -40 -38, -50 -18 C -58 -2, -30 6, -28 -14 C -26 -34, -62 -48, -82 -30 C -94 -18, -88 -2, -76 -4 M2 2 C 6 -10, 16 -14, 22 -10"/>`;
    case 1:
      return `<g ${t} ${line}><path d="M-12 3 C -22 -10, -8 -18, -20 -32"/><path d="M-2 2 C -2 -14, 10 -18, 4 -36"/><path d="M8 2 C 18 -10, 26 -8, 30 -24"/><path d="M14 3 C 26 0, 34 4, 40 -6"/></g>`;
    case 2:
      return `<path ${t} ${line} d="M-2 3 C -8 -16, 4 -30, 16 -24 C 28 -18, 20 -2, 10 -8 C 2 -13, 8 -24, 20 -28"/>`;
    case 3:
      return `<g clip-path="url(#${clipId})"><path fill="${INK}" d="M30 ${top - 20} H210 V${top + 18} C 186 ${top + 20}, 160 ${top + 6}, 138 ${top + 10} C 118 ${top + 14}, 106 ${top + 36}, 82 ${top + 40} C 64 ${top + 42}, 50 ${top + 34}, 30 ${top + 40} Z"/><path fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="2.4" stroke-linecap="round" d="M150 ${top - 2} C 140 ${top + 2}, 128 ${top + 4}, 122 ${top + 10}"/></g>`;
    case 4:
      return `<g clip-path="url(#${clipId})"><path fill="${INK}" d="M30 ${top - 20} H210 V${top + 30} H30 Z"/><path fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="2" d="M70 ${top + 12} H170"/></g>`;
    default:
      return "";
  }
}

const DOODLES = [
  // open book: follows the tried recipe
  `<path d="M0 -8 Q-7 -12 -14 -10 V10 Q-7 8 0 12 Q7 8 14 10 V-10 Q7 -12 0 -8 Z" fill="#fff"/><path d="M0 -8 V12"/><path d="M-10 -3 Q-7 -4.5 -4 -3 M-10 3 Q-7 1.5 -4 3 M4 -3 Q7 -4.5 10 -3 M4 3 Q7 1.5 10 3" stroke-width="2"/>`,
  // gear: keeps the known method and tunes it
  `<path d="M-3.4 -9.9 L-2.9 -13.7 L2.9 -13.7 L3.4 -9.9 L4.6 -9.4 L7.6 -11.7 L11.7 -7.6 L9.4 -4.6 L9.9 -3.4 L13.7 -2.9 L13.7 2.9 L9.9 3.4 L9.4 4.6 L11.7 7.6 L7.6 11.7 L4.6 9.4 L3.4 9.9 L2.9 13.7 L-2.9 13.7 L-3.4 9.9 L-4.6 9.4 L-7.6 11.7 L-11.7 7.6 L-9.4 4.6 L-9.9 3.4 L-13.7 2.9 L-13.7 -2.9 L-9.9 -3.4 L-9.4 -4.6 L-11.7 -7.6 L-7.6 -11.7 L-4.6 -9.4 Z" fill="#fff"/><circle r="4"/>`,
  // light bulb
  `<path d="M-6 8 Q-14 -2 -10 -10 Q-4 -18 4 -16 Q12 -12 10 -2 Q8 4 6 8 Z" fill="#fff"/><path d="M-5 12 H5 M-3 16 H3"/><path d="M14 -14 l4 -4 M18 -2 h5 M-16 -18 l-3 -4"/>`,
  // paper plane
  `<path d="M-14 2 L16 -12 L4 14 L0 4 Z" fill="#fff"/><path d="M0 4 L16 -12"/><path d="M-18 14 q-6 4 -12 2" stroke-dasharray="2 5"/>`,
  // sparkles
  `<path d="M0 -14 Q2 -2 14 0 Q2 2 0 14 Q-2 2 -14 0 Q-2 -2 0 -14 Z" fill="#fff"/><path d="M16 -14 Q17 -10 21 -9 Q17 -8 16 -4 Q15 -8 11 -9 Q15 -10 16 -14 Z" fill="#fff" stroke-width="2.4"/>`,
];

/**
 * SVG markup for one avatar. `steps` maps each trait to 1..5 or null (missing).
 * A missing part uses the neutral stand-in (docs/WorkStyleAvatar.md "Missing answers"):
 * rounded rectangle, no hair, calm face, grey, no doodle, arms at sides. If any
 * answer is missing the body outline is dotted, a status cue rather than a score.
 * `id` must be unique on the page (clip and gradient ids).
 */
export function avatarSvg(steps, { id, doodle = true, label = "" } = {}) {
  const s = (key, fallback) => steps?.[key] ?? fallback;
  const complete = answeredCount(steps ?? {}) === AVATAR_TRAITS.length;
  const col = AVATAR_COLOURS[s("pressure", 0) - 1] ?? PENDING;
  const body = BODIES[s("teamwork", 3) - 1];
  const arms = ARMS[s("leadership", 1) - 1];
  const face = FACES[s("ambiguity", 1) - 1];
  const hairStep = s("structure", null);
  const doodleStep = s("innovation", null);

  const outline = complete
    ? `fill="${INK}" stroke="${INK}" stroke-width="${OUT * 2}" stroke-linejoin="round"`
    : `fill="none" stroke="${INK}" stroke-width="${OUT * 2}" stroke-linecap="round" stroke-dasharray="0.1 9"`;

  const legsInk = LEGS.map((d) => `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${22 + OUT * 2}" stroke-linecap="round" stroke-linejoin="round"/>`).join("");
  const legsCol = LEGS.map((d) => `<path d="${d}" fill="none" stroke="${col.shade}" stroke-width="22" stroke-linecap="round" stroke-linejoin="round"/>`).join("");

  const hands = arms.map(([d, kind]) => hand(d, kind, col.shade));
  const armsInk =
    arms.map(([d]) => `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${15 + OUT * 2}" stroke-linecap="round"/>`).join("") +
    hands.map((h) => `<circle cx="${h.x}" cy="${h.y}" r="${h.r + OUT}" fill="${INK}"/>`).join("");
  const armsCol =
    arms.map(([d]) => `<path d="${d}" fill="none" stroke="${col.shade}" stroke-width="15" stroke-linecap="round"/>`).join("") +
    hands.map((h) => `<circle cx="${h.x}" cy="${h.y}" r="${h.r}" fill="${col.shade}"/>`).join("");
  const fingers = `<g fill="none" stroke="${INK}" stroke-width="2.6" stroke-linecap="round">${hands.map((h) => h.extra).join("")}</g>`;

  const clip = `${id}-clip`;
  const hairSvg = hairStep ? hair(hairStep - 1, body.top, clip) : "";
  const aria = label ? `role="img" aria-label="${label.replace(/"/g, "&quot;")}"` : `aria-hidden="true"`;

  return `<svg viewBox="0 0 240 260" xmlns="http://www.w3.org/2000/svg" ${aria} focusable="false">
<defs><clipPath id="${clip}">${shapes(body.parts, "")}</clipPath><linearGradient id="${id}-grad" x1="0" y1="${body.top}" x2="0" y2="${BODY_BOTTOM}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="${col.light}"/><stop offset=".5" stop-color="${col.main}"/><stop offset="1" stop-color="${col.shade}"/></linearGradient></defs>
<circle cx="120" cy="128" r="116" fill="${col.back}"/>
<g>${legsInk}${legsCol}</g>
<g class="av-body">
<g>${shapes(body.parts, outline)}${shapes(body.parts, `fill="url(#${id}-grad)"`)}</g>
${hairStep >= 4 ? hairSvg : ""}
<g transform="translate(120 106) scale(1.35) translate(-120 -104)" fill="${INK}" stroke="${INK}" stroke-linecap="round" stroke-linejoin="round" stroke-width="0"><g class="av-eyes">${face.eyes}</g>${face.rest}</g>
${hairStep && hairStep <= 3 ? hairSvg : ""}
<g>${armsInk}${armsCol}${fingers}</g>
</g>
${doodle && doodleStep ? `<g transform="translate(204 30)" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">${DOODLES[doodleStep - 1]}</g>` : ""}
</svg>`;
}

/** Thai accessible description: one "part: variant" per answered trait. */
export function avatarLabelTh(steps) {
  const parts = AVATAR_TRAITS.filter((t) => steps?.[t.key] != null).map((t) => `${t.part_th}${t.names_th[steps[t.key] - 1]}`);
  return parts.length ? `ตัวละครจากความชอบในการทำงานของคุณ: ${parts.join(" · ")}` : "ตัวละครที่ยังไม่มีคำตอบ";
}
