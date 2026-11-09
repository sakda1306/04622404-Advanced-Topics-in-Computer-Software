"use client";

import QUESTIONNAIRE from "@/lib/mock/fixtures/questionnaire.json";
import SKILLS from "@/lib/mock/fixtures/skills.json";

// Builds a Contract.md `Profile` from the mock state (confirmed CV, answers and
// chat facts), the way api/app/domain/profile does from its facts list: every
// claim and skill lists the evidence ids it came from (FR-16), and work style is
// reported as a self-reported preference (FR-17).

// The fixtures keep only what the page needs, so the mapping from Design.md
// section 6 (work-style traits, soft-skill ids) is repeated here.
const TRAITS = {
  ws_teamwork: "teamwork",
  ws_structure: "structure",
  ws_ambiguity: "ambiguity",
  ws_pressure: "pressure",
  ws_innovation: "innovation",
  ws_leadership: "leadership",
};
const SOFT_SKILL_OF = {
  ss_adaptability: "adaptability",
  ss_collaboration: "teamwork",
  ss_communication: "communication",
  ss_growth: "self-motivation",
  ss_prioritization: "time-management",
  ss_perseverance: "problem-solving",
  ss_attention_to_detail: "attention-to-detail",
  ss_analytical_thinking: "analytical-thinking",
};
const EXPERIENCE_TEXT = {
  none: "ยังไม่มีประสบการณ์ทำงานด้าน IT",
  projects: "มีประสบการณ์จากโปรเจกต์หรือการฝึกงาน",
  lt_1y: "มีประสบการณ์ทำงานด้าน IT น้อยกว่า 1 ปี",
  "1_3y": "มีประสบการณ์ทำงานด้าน IT 1–3 ปี",
  gt_3y: "มีประสบการณ์ทำงานด้าน IT มากกว่า 3 ปี",
};
const EXPERIENCE_MONTHS = { none: 0, projects: 0, lt_1y: 6, "1_3y": 24, gt_3y: 48 };

const QUESTIONS = QUESTIONNAIRE.sections.flatMap((s) => s.questions);
const QUESTION_NO = Object.fromEntries(QUESTIONS.map((q, i) => [q.question_id, i + 1]));
const QUESTION = Object.fromEntries(QUESTIONS.map((q) => [q.question_id, q]));

export const skillName = (id, fallback) => SKILLS[id]?.th ?? fallback ?? id;
const skillNameEn = (id, fallback) => SKILLS[id]?.en ?? fallback ?? id;

// Names a chat message may use for a skill: the id ("rest-api" → "rest api") and
// the English name before any " / " or "(" ("Docker / containers" → "docker").
const SKILL_KEYS = Object.entries(SKILLS)
  .filter(([, s]) => s.type === "hard")
  .flatMap(([id, s]) => [...new Set([id.replace(/-/g, " "), s.en.split(/ \/ | \(/)[0].toLowerCase()])].map((key) => ({ id, key })))
  .filter(({ key }) => key.length >= 2)
  .sort((x, y) => y.key.length - x.key.length);
const escape = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Skills named in a chat message, with the level typed after them
 * ("Python 3, SQL 2, React Native") → [{skill_id, level}]; level 2 when none.
 * Longer names are matched first, so "React Native" is not also "React".
 */
export function skillsInText(text) {
  let rest = ` ${text.toLowerCase()} `;
  const found = new Map();
  for (const { id, key } of SKILL_KEYS) {
    const re = new RegExp(`(^|[^a-z0-9])${escape(key)}(?![a-z0-9])\\s*(?:(?:จาก\\s*[1-4]\\s*)?เป็น\\s*)?(?:ระดับ\\s*)?([1-4](?![0-9]))?`);
    const m = re.exec(rest);
    if (!m) continue;
    if (!found.has(id)) found.set(id, { skill_id: id, level: m[2] ? Number(m[2]) : 2 });
    rest = rest.slice(0, m.index) + " ".repeat(m[0].length) + rest.slice(m.index + m[0].length);
  }
  return [...found.values()];
}

function optionLabel(questionId, value) {
  return QUESTION[questionId]?.options?.find((o) => o.value === value)?.label_th ?? value;
}

export function buildProfile(state, { version = 1, generatedAt } = {}) {
  const now = new Date().toISOString();
  const evidence = {};
  const add = (e) => {
    evidence[e.id] = e;
    return e.id;
  };
  const cv = state.cv?.status === "confirmed" ? state.cv : null;
  const a = state.answers ?? {};
  const removed = new Set((state.removedSkills ?? []).map((s) => s.skill_id));

  /* hard skills: CV lines, the checklist and chat, merged by skill id (highest level wins) */
  const hard = new Map();
  const put = (id, name, level, evidenceId, years) => {
    const prev = hard.get(id);
    hard.set(id, {
      skill_id: id,
      name_th: skillName(id, name),
      name_en: skillNameEn(id, name),
      kind: "hard",
      level: Math.max(prev?.level ?? 1, level ?? 2),
      ...(years ?? prev?.years ? { years: years ?? prev.years } : {}),
      evidence_ids: [...new Set([...(prev?.evidence_ids ?? []), evidenceId])],
      edited_by_user: false,
    });
  };
  for (const s of cv?.skills ?? []) {
    const id = add({ id: `cv-${s.line_no}`, kind: "cv_line", label_th: `CV บรรทัด ${s.line_no}`, excerpt: s.name });
    put(s.skill_id || s.name.toLowerCase().replace(/\s+/g, "-"), s.name, s.level, id);
  }
  if (Array.isArray(a.sk_tech_stack) && a.sk_tech_stack.length) {
    const id = add({
      id: "ans-sk_tech_stack",
      kind: "answer",
      label_th: `แบบสอบถามข้อ ${QUESTION_NO.sk_tech_stack}`,
      excerpt: a.sk_tech_stack.map((s) => `${skillName(s.skill_id)} ระดับ ${s.level}`).join(", "),
    });
    for (const s of a.sk_tech_stack) put(s.skill_id, null, s.level, id);
  }
  for (const fact of state.chatFacts ?? []) {
    if (!fact.skills?.length) continue;
    const id = add({ id: `chat-${fact.id}`, kind: "chat", label_th: "คำตอบในแชท", excerpt: fact.text });
    for (const s of fact.skills) put(s.skill_id, null, s.level, id);
  }

  /* soft skills: questionnaire answers of 4 or 5 (Design.md section 6) */
  const soft = [];
  for (const [qid, skillId] of Object.entries(SOFT_SKILL_OF)) {
    if (!Number.isInteger(a[qid]) || a[qid] < 4) continue;
    const ids = [
      add({
        id: `ans-${qid}`,
        kind: "answer",
        label_th: `แบบสอบถามข้อ ${QUESTION_NO[qid]}`,
        excerpt: `“${QUESTION[qid].text_th}” ตอบ ${a[qid]}/5`,
      }),
    ];
    soft.push({ skill_id: skillId, name_th: skillName(skillId), name_en: skillNameEn(skillId), kind: "soft", level: a[qid] === 5 ? 3 : 2, evidence_ids: ids, edited_by_user: false });
  }
  const softExample = typeof a.ss_example === "string" && a.ss_example.trim();
  const softChat = (state.chatFacts ?? []).find((f) => f.slot === "soft_skills");
  if (softExample || softChat) {
    const id = softExample
      ? add({ id: "ans-ss_example", kind: "answer", label_th: `แบบสอบถามข้อ ${QUESTION_NO.ss_example}`, excerpt: softExample })
      : add({ id: `chat-${softChat.id}`, kind: "chat", label_th: "คำตอบในแชท", excerpt: softChat.text });
    soft.forEach((s) => s.evidence_ids.push(id));
  }

  /* work style (self-reported, FR-17) */
  const traits = Object.entries(TRAITS)
    .filter(([qid]) => Number.isInteger(a[qid]))
    .map(([qid, trait]) => {
      const value = (a[qid] - 1) / 4;
      const { min_label_th, max_label_th } = QUESTION[qid].scale;
      add({ id: `ans-${qid}`, kind: "answer", label_th: `แบบสอบถามข้อ ${QUESTION_NO[qid]}`, excerpt: `“${QUESTION[qid].text_th}” ตอบ ${a[qid]}/5` });
      return {
        trait,
        value,
        label_th: value <= 0.25 ? min_label_th : value >= 0.75 ? max_label_th : `อยู่ระหว่าง “${min_label_th}” กับ “${max_label_th}”`,
        evidence_id: `ans-${qid}`,
      };
    });
  const wsChat = (state.chatFacts ?? []).find((f) => f.slot === "work_style");
  const leaning = traits.filter((t) => t.value <= 0.25 || t.value >= 0.75).slice(0, 3);
  const workStyleEvidence = traits.map((t) => t.evidence_id);
  if (wsChat) workStyleEvidence.push(add({ id: `chat-${wsChat.id}`, kind: "chat", label_th: "คำตอบในแชท", excerpt: wsChat.text }));
  const summary = leaning.length
    ? `คุณระบุว่าชอบ${leaning.map((t) => t.label_th).join(" · ")}`
    : traits.length
      ? "คุณระบุว่าปรับตัวได้ทั้งสองแบบในเกือบทุกด้าน ไม่ได้ชอบด้านใดด้านหนึ่งชัดเจน"
      : wsChat
        ? `จากแชท: “${wsChat.text}”`
        : "ยังไม่มีข้อมูลความชอบในการทำงาน ตอบแบบสอบถามส่วนนี้หรือเล่าในแชทได้";

  /* experience */
  const expClaims = [];
  let totalMonths = 0;
  for (const e of cv?.experience ?? []) {
    const id = add({ id: `cv-${e.line_no}`, kind: "cv_line", label_th: `CV บรรทัด ${e.line_no}`, excerpt: [e.title, e.summary].filter(Boolean).join(" · ") });
    totalMonths += e.months ?? 0;
    expClaims.push({ text_th: [e.title, e.company].filter(Boolean).join(" · ") + (e.summary ? ` — ${e.summary}` : ""), evidence_ids: [id], edited_by_user: false });
  }
  if (a.ex_it_experience) {
    const id = add({ id: "ans-ex_it_experience", kind: "answer", label_th: `แบบสอบถามข้อ ${QUESTION_NO.ex_it_experience}`, excerpt: optionLabel("ex_it_experience", a.ex_it_experience) });
    if (!cv?.experience?.length) totalMonths = EXPERIENCE_MONTHS[a.ex_it_experience] ?? 0;
    expClaims.push({ text_th: EXPERIENCE_TEXT[a.ex_it_experience] ?? optionLabel("ex_it_experience", a.ex_it_experience), evidence_ids: [id], edited_by_user: false });
  }
  for (const f of (state.chatFacts ?? []).filter((f) => f.slot === "experience")) {
    const id = add({ id: `chat-${f.id}`, kind: "chat", label_th: "คำตอบในแชท", excerpt: f.text });
    expClaims.push({ text_th: f.text, evidence_ids: [id], edited_by_user: false });
  }
  for (const e of cv?.education ?? []) {
    const id = add({ id: `cv-${e.line_no}`, kind: "cv_line", label_th: `CV บรรทัด ${e.line_no}`, excerpt: `${e.school} ${e.field ?? ""}`.trim() });
    expClaims.push({ text_th: `${e.degree ?? "การศึกษา"} ${e.field ?? ""} · ${e.school}${e.end ? ` (${e.end})` : ""}`, evidence_ids: [id], edited_by_user: false });
  }

  /* blind spots: low self-ratings, basic-level skills, and areas with no evidence */
  const blind = [];
  const roleNote = add({ id: "rag-role-skills", kind: "rag_chunk", label_th: "บันทึกทักษะสายงาน (ทีมผู้พัฒนา)", excerpt: "สายงานพัฒนาซอฟต์แวร์ส่วนใหญ่ต้องการ Git, การทดสอบ และการ deploy ขึ้น cloud หรือ container" });
  const hardList = [...hard.values()].filter((s) => !removed.has(s.skill_id));
  const basic = hardList.filter((s) => s.level === 1);
  if (basic.length) {
    blind.push({ text_th: `${basic.map((s) => s.name_th).join(", ")} ยังอยู่ระดับเริ่มต้น ถ้าสนใจสายงานที่ใช้ทักษะนี้ ลองทำโปรเจกต์เล็ก ๆ เพิ่ม`, evidence_ids: basic.flatMap((s) => s.evidence_ids).slice(0, 2), edited_by_user: false });
  }
  for (const [qid, skillId] of Object.entries(SOFT_SKILL_OF)) {
    if (!Number.isInteger(a[qid]) || a[qid] > 2) continue;
    blind.push({
      text_th: `คุณให้คะแนนตัวเองด้าน${skillName(skillId)}ค่อนข้างต่ำ ลองหาโอกาสฝึกในงานกลุ่มหรือโปรเจกต์`,
      evidence_ids: [add({ id: `ans-${qid}`, kind: "answer", label_th: `แบบสอบถามข้อ ${QUESTION_NO[qid]}`, excerpt: `“${QUESTION[qid].text_th}” ตอบ ${a[qid]}/5` })],
      edited_by_user: false,
    });
  }
  const has = (ids) => ids.some((id) => hardList.some((s) => s.skill_id === id));
  if (!has(["docker", "kubernetes", "aws", "gcp", "azure", "ci-cd", "cloud-computing"])) {
    blind.push({ text_th: "ยังไม่พบหลักฐานทักษะการ deploy เช่น Docker หรือ Cloud ซึ่งหลายสายงานต้องใช้", evidence_ids: [roleNote], edited_by_user: false });
  }
  if (!has(["unit-testing", "test-automation", "manual-testing", "regression-testing"])) {
    blind.push({ text_th: "ยังไม่พบหลักฐานเรื่องการเขียนเทสต์ เล่าในแชทได้ถ้าคุณเคยทำ", evidence_ids: [roleNote], edited_by_user: false });
  }
  if (!blind.some((b) => b.evidence_ids.includes(roleNote))) delete evidence[roleNote];

  /* preferences (goals) */
  const salaryMid = { lt_20k: 18000, "20k_30k": 25000, "30k_45k": 37500, "45k_60k": 52500, gt_60k: 70000 };
  const preferences = {
    interested_roles: Array.isArray(a.go_interested_roles) ? a.go_interested_roles : [],
    ...(salaryMid[a.go_salary] ? { desired_salary_thb: salaryMid[a.go_salary] } : {}),
    locations: a.go_location ? [a.go_location] : [],
    work_style: Object.fromEntries(traits.map((t) => [t.trait, t.value])),
  };

  return {
    profile_version: version,
    generated_at: generatedAt ?? now,
    updated_at: now,
    hard_skills: hardList.sort((x, y) => y.level - x.level || x.name_th.localeCompare(y.name_th, "th")),
    soft_skills: soft.filter((s) => !removed.has(s.skill_id)).sort((x, y) => y.level - x.level),
    work_style: {
      summary_th: summary,
      summary_evidence_ids: workStyleEvidence,
      // summary_evidence_ids and traits[].evidence_ids are not in Contract.md 0.3 yet
      // (proposed so work style can cite its answers, FR-16); the page treats them as optional.
      traits: traits.map(({ trait, value, label_th, evidence_id }) => ({ trait, value, label_th, evidence_ids: [evidence_id] })),
      disclaimer_th: "ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ",
    },
    experience: { total_months: totalMonths, summary: expClaims },
    blind_spots: blind,
    preferences,
    evidence,
  };
}
