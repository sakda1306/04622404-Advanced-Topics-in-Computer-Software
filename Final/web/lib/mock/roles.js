"use client";

import ROLES from "@/lib/mock/fixtures/roles.json";
import { skillName } from "@/lib/mock/profile";

// Mock role matching (Design.md 4.3), role detail (Contract.md RoleDetail) and
// role market data (RoleMarket) built from the role files in /data. Scoring is
// the same formula the api runs in Python; reasons and next steps stand in for
// the LLM text and always tie each step to a gap id.

export const THRESHOLD = 60;
const TOP_N = 5;
const BY_ID = Object.fromEntries(ROLES.map((r) => [r.role_id, r]));
export const roleById = (id) => BY_ID[id] ?? null;

const sum = (xs) => xs.reduce((a, b) => a + b, 0);
const groupName = (skills) => skills.map((id) => skillName(id)).join(" / ");

export function roleCatalogue() {
  return ROLES.map(({ role_id, title_th, title_en, career_stage, description_th }) => ({
    role_id,
    title_th,
    title_en,
    summary_th: description_th.split("\n")[0],
    career_stage,
  }));
}

export function roleDetail(role) {
  return {
    role_id: role.role_id,
    title_th: role.title_th,
    title_en: role.title_en,
    description_th: role.description_th,
    career_stage: role.career_stage,
    required: role.required.map((q) => ({ skills: q.skills.map((id) => ({ skill_id: id, name_th: skillName(id) })), min_level: q.min_level, weight: q.weight })),
    nice_to_have: role.nice_to_have.map((id) => ({ skill_id: id, name_th: skillName(id) })),
    soft_skills: role.soft_skills.map((id) => ({ skill_id: id, name_th: skillName(id) })),
    learning_path_th: role.learning_path_th,
    author: role.author,
    reviewer: role.reviewer,
    status: role.status,
    sources: role.sources,
  };
}

function scoreRole(role, profile) {
  const hard = Object.fromEntries(profile.hard_skills.map((s) => [s.skill_id, s]));
  const soft = new Set(profile.soft_skills.map((s) => s.skill_id));
  const matched = [];
  const gaps = [];

  const reqScores = role.required.map((q, i) => {
    const best = q.skills.map((id) => hard[id]).filter(Boolean).sort((x, y) => y.level - x.level)[0];
    if (!best) {
      gaps.push({ gap_id: `${role.role_id}-req-${i}`, kind: "missing_skill", skill_id: q.skills[0], name_th: groupName(q.skills), required_level: q.min_level, weight: q.weight });
      return 0;
    }
    matched.push({ skill_id: best.skill_id, name_th: best.name_th, evidence_ids: best.evidence_ids });
    if (best.level < q.min_level) {
      gaps.push({ gap_id: `${role.role_id}-req-${i}`, kind: "below_level", skill_id: best.skill_id, name_th: best.name_th, required_level: q.min_level, user_level: best.level, weight: q.weight });
    }
    return Math.min(best.level / q.min_level, 1);
  });
  const hardRequired = sum(role.required.map((q, i) => q.weight * reqScores[i])) / sum(role.required.map((q) => q.weight));

  const niceHave = role.nice_to_have.filter((id) => hard[id]);
  for (const id of niceHave) matched.push({ skill_id: id, name_th: hard[id].name_th, evidence_ids: hard[id].evidence_ids });
  const hardNice = role.nice_to_have.length ? niceHave.length / role.nice_to_have.length : 0;

  const softHave = role.soft_skills.filter((id) => soft.has(id));
  for (const id of role.soft_skills.filter((id) => !soft.has(id))) {
    gaps.push({ gap_id: `${role.role_id}-soft-${id}`, kind: "soft_skill", skill_id: id, name_th: skillName(id), weight: 0 });
  }
  const softScore = role.soft_skills.length ? softHave.length / role.soft_skills.length : 0;

  const prefs = profile.preferences?.work_style ?? {};
  const traits = Object.keys(role.work_style).filter((t) => typeof prefs[t] === "number");
  const workStyle = traits.length ? 1 - sum(traits.map((t) => Math.abs(prefs[t] - role.work_style[t]))) / traits.length : 0.5;

  const breakdown = { hard_required: hardRequired, hard_nice: hardNice, soft: softScore, work_style: workStyle };
  const match_pct = Math.round(100 * (0.7 * hardRequired + 0.15 * hardNice + 0.1 * softScore + 0.05 * workStyle));

  // Gaps: missing required (by weight), then below level, then soft skills.
  const order = { missing_skill: 0, below_level: 1, soft_skill: 2 };
  gaps.sort((x, y) => order[x.kind] - order[y.kind] || y.weight - x.weight);
  return { match_pct, breakdown, matched, gaps: gaps.map(({ weight: _w, ...g }) => g) };
}

function nextSteps(role, gaps) {
  return gaps.slice(0, TOP_N).map((g, i) => ({
    gap_id: g.gap_id,
    priority: i + 1,
    action_th:
      g.kind === "missing_skill"
        ? `เริ่มเรียน ${g.name_th} ให้ถึงระดับ ${g.required_level} แล้วทำโปรเจกต์เล็ก ๆ ที่ใช้จริง และใส่ไว้ใน CV`
        : g.kind === "below_level"
          ? `ฝึก ${g.name_th} จากระดับ ${g.user_level} ให้ถึงระดับ ${g.required_level} เช่น ทำโจทย์ที่ซับซ้อนขึ้นในโปรเจกต์ของคุณ`
          : `หาโอกาสฝึก${g.name_th}ในงานกลุ่ม แล้วเล่าตัวอย่างนั้นในแชทเพื่อเพิ่มหลักฐาน`,
  }));
}

function reason(role, scored) {
  const top = scored.matched.slice(0, 3).map((m) => m.name_th);
  if (!top.length) return `ยังไม่พบทักษะที่ตรงกับ ${role.title_th} ในโปรไฟล์ของคุณ`;
  const firstGap = scored.gaps[0];
  return `คุณมี ${top.join(", ")} ซึ่งเป็นทักษะหลักของ${role.title_th}${firstGap ? ` สิ่งที่ควรเติมก่อนคือ ${firstGap.name_th}` : ""}`;
}

/** RoleMatch for one role; `stale` keeps the earlier wording and flags it (FR-32). */
export function matchRole(role, profile, { stale = false } = {}) {
  const scored = scoreRole(role, profile);
  return {
    role_id: role.role_id,
    title_th: role.title_th,
    match_pct: scored.match_pct,
    breakdown: scored.breakdown,
    matched: scored.matched,
    gaps: scored.gaps,
    reason_th: stale ? null : reason(role, scored),
    next_steps: stale ? [] : nextSteps(role, scored.gaps),
    explanations_stale: stale,
  };
}

/** MatchList: top 5 at or above the threshold, else the 3 closest (FR-19a). */
export function matchList(profile, { stale = false } = {}) {
  const all = ROLES.map((r) => matchRole(r, profile, { stale })).sort((x, y) => y.match_pct - x.match_pct);
  const passing = all.filter((m) => m.match_pct >= THRESHOLD);
  return {
    profile_version: profile.profile_version,
    threshold: THRESHOLD,
    below_threshold: passing.length === 0,
    roles: passing.length ? passing.slice(0, TOP_N) : all.slice(0, 3),
  };
}

/* ---------- market (Contract.md 2.7) ---------- */

// Small stable hash so each role gets the same mock numbers on every load.
function seed(text) {
  let h = 2166136261;
  for (const ch of text) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return (h >>> 0) / 4294967295;
}

const COMPANIES = ["บริษัทตัวอย่าง เทคโนโลยี จำกัด", "บริษัทตัวอย่าง ดิจิทัล โซลูชันส์", "บริษัทตัวอย่าง ฟินเทค", "บริษัทตัวอย่าง ซอฟต์แวร์เฮาส์", "บริษัทตัวอย่าง ค้าปลีกออนไลน์"];

/**
 * Scenarios: `devops-engineer` has no cache yet and a refresh running (becomes
 * available ~12 s after it is first opened); `cloud-engineer` is stale.
 */
export function roleMarket(role, { firstOpenedAt, now = Date.now(), listings = 5 }) {
  const id = role.role_id;
  const fetchedAt = new Date(Date.UTC(2026, 10, 1, 3, 0)).toISOString();
  const disclaimer_th = "ข้อมูลประกาศงานรวบรวมจากแหล่งที่ไม่เป็นทางการ อาจไม่ครบถ้วน";
  if (id === "devops-engineer" && now - firstOpenedAt < 12000) {
    return { role_id: id, location_scope: "bangkok", available: false, fetched_at: null, stale: false, refreshing: true, salary: { advertised: null, reference: null, baseline: null }, demand: null, listings: [], disclaimer_th };
  }

  const r = seed(id);
  const ref = role.salary_reference;
  const base = ref ? (ref.min_thb + ref.max_thb) / 2 : 30000 + Math.round(r * 20) * 1000;
  const postings = 6 + Math.round(r * 14);
  const advMin = Math.round((base * (0.8 + r * 0.1)) / 1000) * 1000;
  const advMax = Math.round((base * (1.25 + r * 0.2)) / 1000) * 1000;
  const skills = [...role.required.map((q) => q.skills[0]), ...role.nice_to_have].slice(0, 8);

  return {
    role_id: id,
    location_scope: "bangkok",
    available: true,
    fetched_at: id === "cloud-engineer" ? new Date(Date.UTC(2026, 9, 20, 3, 0)).toISOString() : fetchedAt,
    stale: id === "cloud-engineer",
    refreshing: false,
    salary: {
      advertised: {
        min_thb: advMin,
        max_thb: advMax,
        measure: "monthly_base",
        source: "JobThai (ประกาศงาน)",
        source_type: "advertised",
        sample_size: Math.max(3, Math.round(postings * 0.6)),
        as_of: fetchedAt.slice(0, 10),
      },
      reference: ref ? { ...ref, source_type: "curated_reference" } : null,
      baseline: {
        min_thb: 33500,
        max_thb: 33500,
        measure: "monthly_base",
        source: "สำนักงานสถิติแห่งชาติ",
        source_type: "official_baseline",
        as_of: "2026-09-30",
      },
    },
    demand: {
      posting_count: postings,
      trending_skills: skills.map((s, i) => ({ skill_id: s, name_th: skillName(s), count: Math.max(1, Math.round(postings * (0.85 - i * 0.1))) })),
    },
    listings: Array.from({ length: Math.min(listings, 5) }, (_, i) => ({
      title: i === 0 ? role.title_en : `${i % 2 ? "Junior " : ""}${role.title_en}`,
      company: COMPANIES[(i + Math.round(r * 10)) % COMPANIES.length],
      location: "กรุงเทพฯ",
      ...(i % 3 !== 2 ? { salary_text: `${(advMin + i * 2000).toLocaleString("en-US")} - ${(advMax - i * 2000).toLocaleString("en-US")} บาท` } : {}),
      posted_at: new Date(Date.UTC(2026, 9, 31 - i * 2)).toISOString(),
      url: `https://www.jobthai.com/th/jobs?keyword=${encodeURIComponent(role.title_en)}`,
      source: "JobThai",
    })),
    disclaimer_th,
  };
}
