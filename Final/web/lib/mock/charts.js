// MOCK DATA for /examples/charts only. Not real user data.
// The role requirements follow data/roles/backend-developer.json; the user's
// levels are invented. Scores use the formula in Design.md section 4.3 so the
// numbers on the page agree with each other.

export const role = { role_id: "backend-developer", title_th: "นักพัฒนาแบ็กเอนด์", title_en: "Backend Developer" };

// Required skills (any-of group shown as one axis). Levels: 0 none … 4 expert.
export const requiredSkills = [
  { key: "lang", label: "Python / Java / Node.js", weight: 3, minLevel: 2, userLevel: 3 },
  { key: "sql", label: "SQL", weight: 3, minLevel: 2, userLevel: 1 },
  { key: "rest", label: "REST API", weight: 3, minLevel: 2, userLevel: 2 },
  { key: "dbdesign", label: "ออกแบบฐานข้อมูล", weight: 2, minLevel: 1, userLevel: 1 },
  { key: "git", label: "Git", weight: 1, minLevel: 1, userLevel: 3 },
  { key: "linux", label: "Linux", weight: 1, minLevel: 1, userLevel: 0 },
];

const niceToHave = { total: 9, have: ["docker", "unit-testing", "postgresql"] };
const softSkills = { total: 4, have: ["problem-solving", "teamwork", "communication"] };

// Work style: role value 0..1, user answer 1..5 -> (answer - 1) / 4.
export const workStyle = [
  { trait: "teamwork", low: "ทำงานคนเดียว", high: "ทำงานกับทีมตลอด", role: 0.6, answer: 4 },
  { trait: "structure", low: "ใช้วิธีของตัวเอง", high: "มีขั้นตอนชัดเจน", role: 0.6, answer: 3 },
  { trait: "ambiguity", low: "อยากได้โจทย์ชัด", high: "ชอบโจทย์ปลายเปิด", role: 0.5, answer: 4 },
  { trait: "pressure", low: "จังหวะคงที่", high: "งานด่วน เส้นตายแน่น", role: 0.5, answer: 2 },
  { trait: "innovation", low: "วิธีที่พิสูจน์แล้ว", high: "วิธีและเครื่องมือใหม่", role: 0.5, answer: 5 },
  { trait: "leadership", low: "ทำส่วนของตัวเอง", high: "นำและประสานงาน", role: 0.3, answer: 2 },
].map((w) => ({ ...w, user: (w.answer - 1) / 4 }));

const sum = (xs) => xs.reduce((a, b) => a + b, 0);
const hardRequired =
  sum(requiredSkills.map((s) => s.weight * Math.min(s.userLevel / s.minLevel, 1))) / sum(requiredSkills.map((s) => s.weight));
const hardNice = niceToHave.have.length / niceToHave.total;
const soft = softSkills.have.length / softSkills.total;
const workStyleScore = 1 - sum(workStyle.map((w) => Math.abs(w.user - w.role))) / workStyle.length;

// Points earned out of the maximum for each part (70 + 15 + 10 + 5 = 100).
export const breakdown = [
  { key: "hard_required", label: "ทักษะที่ต้องมี", max: 70, earned: 70 * hardRequired, detail: "ถ่วงน้ำหนักตามความสำคัญ" },
  { key: "hard_nice", label: "ทักษะที่ควรมี", max: 15, earned: 15 * hardNice, detail: `${niceToHave.have.length} จาก ${niceToHave.total} ทักษะ` },
  { key: "soft", label: "Soft skills", max: 10, earned: 10 * soft, detail: `${softSkills.have.length} จาก ${softSkills.total} ทักษะ` },
  { key: "work_style", label: "รูปแบบการทำงาน", max: 5, earned: 5 * workStyleScore, detail: "ความใกล้เคียงของความชอบ" },
];

export const matchPct = Math.round(sum(breakdown.map((b) => b.earned)));
export const completeness = 64; // profile completeness meter, 0..100

export const salary = [
  { key: "advertised", label: "ที่ประกาศในงาน", min: 28000, max: 52000, source: "JobThai (ประกาศงาน)", detail: "จาก 14 ประกาศที่ระบุเงินเดือน", asOf: "2026-10-28" },
  { key: "reference", label: "ตารางอ้างอิง", min: 25000, max: 45000, source: "Jobsdb ไทย", detail: "เงินเดือนเริ่มต้น", asOf: "2026-06-08" },
  { key: "baseline", label: "ค่าจ้างอุตสาหกรรม IT", value: 33500, source: "สำนักงานสถิติแห่งชาติ", detail: "ตัวเลขเดียวตามอุตสาหกรรม", asOf: "2026-09-30" },
];

export const trendingSkills = {
  postings: 14,
  skills: [
    { name: "SQL", count: 11 },
    { name: "ภาษา Python", count: 9 },
    { name: "REST API", count: 8 },
    { name: "Docker", count: 7 },
    { name: "Git", count: 6 },
    { name: "Linux", count: 5 },
    { name: "ภาษา Java", count: 4 },
    { name: "AWS", count: 3 },
  ],
};

// ---- admin dashboard -------------------------------------------------------

export const adminStats = [
  { key: "requests", label: "คำขอวันนี้", value: 1284, format: "num" },
  { key: "users", label: "ผู้ใช้ที่ใช้งานวันนี้", value: 23, format: "num" },
  { key: "error_rate", label: "อัตราข้อผิดพลาด", value: 1.8, format: "pct1", warnAbove: 5 },
  { key: "p95", label: "เวลาตอบ AI (p95)", value: 8.4, format: "sec", target: 15 },
];

export const llmUsage = [
  { key: "main-tokens", label: "openai/gpt-oss-120b · tokens", used: 142300, limit: 200000 },
  { key: "router-tokens", label: "qwen/qwen3.8-27b · tokens", used: 168900, limit: 200000 },
  { key: "main-requests", label: "openai/gpt-oss-120b · requests", used: 612, limit: 1000 },
  { key: "apify", label: "Apify runs สัปดาห์นี้", used: 19, limit: 26 },
];

export const routerShare = [
  { route: "gap_question", share: 0.34 },
  { route: "job_matching", share: 0.21 },
  { route: "skill_assessment", share: 0.14 },
  { route: "salary", share: 0.1 },
  { route: "profile_edit", share: 0.08 },
  { route: "market", share: 0.06 },
  { route: "อื่น ๆ", share: 0.07 },
];

// Deterministic daily series so the page looks the same on every load.
function series(days) {
  const out = [];
  const end = new Date("2026-11-01T00:00:00+07:00");
  for (let i = days - 1; i >= 0; i -= 1) {
    const d = new Date(end);
    d.setDate(end.getDate() - i);
    const t = days - i;
    const wave = Math.sin(t / 2.3) * 120 + Math.cos(t / 5.1) * 80;
    const total = Math.round(700 + t * (days > 7 ? 14 : 60) + wave);
    out.push({ date: d.toISOString().slice(0, 10), total, ai: Math.round(total * (0.38 + 0.05 * Math.sin(t / 3))) });
  }
  return out;
}
export const requestsByDay = { "7d": series(7), "30d": series(30) };
