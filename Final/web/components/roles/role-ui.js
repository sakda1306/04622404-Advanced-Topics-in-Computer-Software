"use client";

import { AlertTriangle, CheckCircle2, CircleDashed, Info, TrendingDown } from "lucide-react";
import { Cite } from "@/components/app/citation";

// Small pieces shared by the role results and role detail pages
// (DesignSystem.md section 3: role match card, required skill list).

export const STAGE_TH = { entry: "เริ่มต้น", mid: "ระดับกลาง", senior: "อาวุโส" };
export const WEIGHT_TH = { 3: "สำคัญมาก", 2: "สำคัญ", 1: "ควรมี" };
export const MATCH_DISCLAIMER = "คำนวณจากทักษะที่ตรงกับสายงาน ไม่ใช่การรับประกันการได้งาน";

export function StageBadge({ stage }) {
  if (!STAGE_TH[stage]) return null;
  return (
    <span className="inline-flex items-center rounded-full border border-border bg-bg px-2.5 py-0.5 text-tiny font-medium text-text-muted">
      {STAGE_TH[stage]}
    </span>
  );
}

/** A mid or senior role usually needs work experience, which explains a lower score for a fresh graduate. */
export function ExperienceNote({ stage }) {
  if (stage !== "mid" && stage !== "senior") return null;
  return (
    <p className="flex items-start gap-1.5 text-tiny text-info">
      <Info className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
      สายงาน{STAGE_TH[stage]}มักต้องมีประสบการณ์ทำงาน คะแนนจึงอาจต่ำกว่าสำหรับผู้เพิ่งจบ
    </p>
  );
}

/** Match % as a large number and a bar with the threshold marked. */
export function MatchMeter({ pct, threshold, size = "md" }) {
  const pass = pct >= threshold;
  return (
    <div>
      <div className="flex items-end gap-3">
        <span className={`tabular font-[family-name:var(--font-latin-first)] leading-none font-semibold text-accent ${size === "lg" ? "text-[48px]" : "text-[36px]"}`}>
          {pct}
          <span className="text-h3">%</span>
        </span>
        {!pass && (
          <span className="mb-1 inline-flex items-center gap-1 rounded-full border border-warning px-2 py-0.5 text-tiny font-medium text-warning">
            <TrendingDown className="size-3.5" strokeWidth={2} aria-hidden="true" />
            ต่ำกว่าเกณฑ์ {threshold}%
          </span>
        )}
      </div>
      <div
        role="progressbar"
        aria-label="ความตรงกับสายงาน"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="relative mt-3 h-2.5 rounded-full bg-border"
      >
        <div className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out" style={{ width: `${pct}%` }} />
        <span className="absolute -top-1 h-4.5 w-0.5 rounded-full bg-text-muted" style={{ left: `${threshold}%` }} aria-hidden="true" />
      </div>
    </div>
  );
}

export function MatchedSkill({ skill }) {
  return (
    <li className="flex items-start gap-2 text-small text-text">
      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" strokeWidth={2} aria-hidden="true" />
      <span>
        <span className="sr-only">มีแล้ว: </span>
        {skill.name_th}
        <Cite ids={skill.evidence_ids?.slice(0, 1)} />
      </span>
    </li>
  );
}

/** A gap: missing = warning colour + icon + "ยังไม่มี" (never colour alone). */
export function GapLabel({ gap }) {
  const text =
    gap.kind === "missing_skill"
      ? `ยังไม่มี · ต้องการระดับ ${gap.required_level}`
      : gap.kind === "below_level"
        ? `ต่ำกว่าระดับ · มี ${gap.user_level} ต้องการ ${gap.required_level}`
        : "ยังไม่มีหลักฐาน";
  const Icon = gap.kind === "soft_skill" ? CircleDashed : AlertTriangle;
  return (
    <span className="flex items-start gap-2 text-small text-text">
      <Icon className="mt-0.5 size-4 shrink-0 text-warning" strokeWidth={2} aria-hidden="true" />
      <span>
        {gap.name_th}
        <span className="ml-1.5 text-tiny text-warning">{text}</span>
      </span>
    </span>
  );
}

/** Next steps, each linked to the gap it closes (FR-20a). */
export function NextSteps({ steps, gaps, limit = 5 }) {
  const byId = Object.fromEntries(gaps.map((g) => [g.gap_id, g]));
  const list = [...steps].sort((a, b) => a.priority - b.priority).slice(0, limit).filter((s) => byId[s.gap_id]);
  if (!list.length) return null;
  return (
    <ol className="space-y-2.5">
      {list.map((s, i) => (
        <li key={s.gap_id} className="flex gap-3 text-small text-text">
          <span className="tabular inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-primary-subtle text-tiny font-semibold">{i + 1}</span>
          <span>
            {s.action_th}
            <span className="mt-0.5 block text-tiny text-text-muted">ปิดช่องว่าง: {byId[s.gap_id].name_th}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
