"use client";

import ROLES from "@/lib/mock/fixtures/roles.json";

// Mock AdminOverview (Contract.md 2.9, PRD FR-43 – FR-44): aggregates only, no
// user content (FR-42). Numbers are invented but consistent with each other and
// stable for a window, so the page looks the same on every refresh. A few states
// are built in to show the warnings: the main model above 80% of its daily
// tokens, two stale role caches, one cache with an error, one refreshing.

const WARN_LLM_PCT = 80;
const WARN_ERROR_PCT = 5;
const CACHE_MAX_AGE_DAYS = 7;
const APIFY_BUDGET = 26;

const SCALE = { today: 1, "7d": 6.2, "30d": 24 };
// New users grow slower than requests: most users come back on later days.
const USER_SCALE = { today: 1, "7d": 3, "30d": 6 };
const round = (n) => Math.round(n);
const ratio = (n) => Math.round(n * 1000) / 1000;

const CACHE_STATE = {
  "frontend-developer": { age: 8 },
  "data-engineer": { age: 9, error: "PROVIDER_TIMEOUT" },
  "devops-engineer": { age: null, refreshing: true },
};

function cacheRows(now) {
  return ROLES.map((r, i) => {
    const s = CACHE_STATE[r.role_id] ?? { age: 1 + (i % 6) };
    const fetched = s.age === null ? null : new Date(now.getTime() - s.age * 86400000 - (i % 5) * 3600000);
    const postings = s.age === null ? 0 : 8 + ((i * 7) % 13);
    return {
      role_id: r.role_id,
      title_th: r.title_th,
      fetched_at: fetched?.toISOString() ?? null,
      age_days: s.age,
      stale: s.age !== null && (s.age > CACHE_MAX_AGE_DAYS || Boolean(s.error)),
      refreshing: Boolean(s.refreshing),
      last_error: s.error ?? null,
      posting_count: postings,
      salary_parsed_share: postings ? ratio(0.35 + ((i * 13) % 40) / 100) : 0,
      has_reference_salary: Boolean(r.salary_reference),
    };
  });
}

export function adminOverview(window = "today", now = new Date()) {
  const k = SCALE[window] ?? 1;
  const requests = round(2480 * k);
  const errorsByCode = [
    { code: "LLM_TIMEOUT", count: round(22 * k) },
    { code: "RATE_LIMITED", count: round(14 * k) },
    { code: "INTERNAL_ERROR", count: round(12 * k) },
    { code: "LLM_UNAVAILABLE", count: round(11 * k) },
    { code: "QUOTA_EXCEEDED", count: round(9 * k) },
    { code: "VALIDATION_ERROR", count: round(6 * k) },
  ];
  const fiveXx = errorsByCode.filter((e) => ["LLM_TIMEOUT", "INTERNAL_ERROR", "LLM_UNAVAILABLE"].includes(e.code)).reduce((s, e) => s + e.count, 0);
  const errorRate = ratio(fiveXx / requests);

  const models = [
    { model: "openai/gpt-oss-120b", role: "main", tokens_used: 168000, tokens_limit: 200000, requests_used: 620, requests_limit: 1000 },
    { model: "qwen/qwen3.8-27b", role: "router", tokens_used: 82000, tokens_limit: 200000, requests_used: 810, requests_limit: 1000 },
    { model: "qwen/qwen3.8-27b · fallback", role: "fallback", tokens_used: 24000, tokens_limit: 200000, requests_used: 68, requests_limit: 1000 },
  ];
  const roles = cacheRows(now);
  const apifyRuns = 19;

  const warnings = [];
  for (const m of models) {
    const pct = Math.max(m.tokens_used / m.tokens_limit, m.requests_used / m.requests_limit) * 100;
    if (pct > WARN_LLM_PCT) {
      warnings.push({ panel: "llm", code: "LLM_NEAR_LIMIT", message_th: `โมเดล ${m.model} ใช้โควตาวันนี้ไปแล้ว ${Math.round(pct)}% (เกิน ${WARN_LLM_PCT}%)` });
    }
  }
  if (errorRate * 100 > WARN_ERROR_PCT) {
    warnings.push({ panel: "health", code: "ERROR_RATE_HIGH", message_th: `อัตราข้อผิดพลาด ${(errorRate * 100).toFixed(1)}% (เกิน ${WARN_ERROR_PCT}%)` });
  }
  const stale = roles.filter((r) => r.age_days !== null && r.age_days > CACHE_MAX_AGE_DAYS);
  if (stale.length) warnings.push({ panel: "cache", code: "CACHE_STALE", message_th: `ข้อมูลตลาดงาน ${stale.length} สายงานเก่ากว่า ${CACHE_MAX_AGE_DAYS} วัน` });
  for (const r of roles.filter((x) => x.last_error)) {
    warnings.push({ panel: "cache", code: "CACHE_ERROR", message_th: `ดึงข้อมูล ${r.title_th} ไม่สำเร็จ (${r.last_error}) ระบบใช้ข้อมูลเดิมและจะลองใหม่รอบถัดไป` });
  }
  if (apifyRuns > APIFY_BUDGET) warnings.push({ panel: "cache", code: "APIFY_OVER_BUDGET", message_th: `ใช้ Apify ${apifyRuns} ครั้งในสัปดาห์นี้ เกินงบ ${APIFY_BUDGET} ครั้ง` });

  const u = USER_SCALE[window] ?? 1;
  const registered = round(180 * u);
  return {
    generated_at: now.toISOString(),
    window,
    warnings,
    health: {
      api: "ok",
      db: "ok",
      last_request_at: new Date(now.getTime() - 42000).toISOString(),
      requests,
      error_rate: errorRate,
      errors_by_code: errorsByCode,
      llm_latency_ms: { p50: 4800, p95: 12600, target: 15000 },
    },
    llm: { day: now.toISOString().slice(0, 10), models, rate_limited_429: 14, fallback_calls: 68 },
    quota: { requests_used: 1906, tokens_used: 274000, users_active: 136, users_exhausted: 8, users_over_80pct: 19 },
    cache: { apify_runs_this_week: apifyRuns, apify_runs_budget: APIFY_BUDGET, roles },
    router: {
      messages: round(1260 * k),
      by_route: [
        { route: "gap_question", share: 0.3 },
        { route: "skill_assessment", share: 0.16 },
        { route: "job_matching", share: 0.14 },
        { route: "experience", share: 0.1 },
        { route: "profile_edit", share: 0.09 },
        { route: "salary", share: 0.08 },
        { route: "market", share: 0.05 },
        { route: "work_style", share: 0.03 },
        { route: "blind_spots", share: 0.02 },
        { route: "clarify", share: 0.02 },
        { route: "decline", share: 0.01 },
      ],
      by_layer: { rules: 0.56, llm: 0.38, guard: 0.06 },
      clarify_rate: 0.07,
      decline_rate: 0.02,
      low_confidence_rate: 0.05,
    },
    funnel: {
      registered,
      with_cv_or_questionnaire: round(registered * 0.8),
      profile_generated: round(registered * 0.62),
      role_opened: round(registered * 0.48),
      cv_unreadable_rate: 0.06,
      input_mix: { cv_only: 0.44, questionnaire_only: 0.31, both: 0.25 },
      avg_completeness_at_generate: 76,
      edits: { applied: round(68 * u), rejected: round(14 * u), expired: round(8 * u) },
      top_removed_skills: [
        { skill_id: "docker", name_th: "Docker และคอนเทนเนอร์", count: 28 },
        { skill_id: "react", name_th: "React", count: 19 },
        { skill_id: "sql", name_th: "SQL", count: 16 },
        { skill_id: "python", name_th: "Python", count: 12 },
        { skill_id: "git", name_th: "Git และการควบคุมเวอร์ชัน", count: 9 },
      ],
    },
  };
}
