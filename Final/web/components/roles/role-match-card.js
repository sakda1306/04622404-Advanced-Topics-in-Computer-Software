"use client";

import Link from "next/link";
import { ArrowRight, Star } from "lucide-react";
import { Cite } from "@/components/app/citation";
import { ExperienceNote, GapLabel, MatchedSkill, MatchMeter, NextSteps, StageBadge } from "@/components/roles/role-ui";

/** Star + text, so the goal mark never relies on colour alone. */
export function GoalBadge({ label = "เป้าหมายของคุณ" }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary-subtle px-2.5 py-0.5 text-tiny font-semibold text-text">
      <Star className="size-3.5 fill-current text-accent" strokeWidth={2} aria-hidden="true" />
      {label}
    </span>
  );
}

// Role match card (DesignSystem.md section 3): title, career-stage badge, match %
// (number + bar), top matched skills, gaps, reason with citations, up to 5 next
// steps each linked to its gap, and "ดูรายละเอียด". The below-threshold variant
// (closest role, FR-19a) puts what is missing first. `goal` marks a role the user
// picked in the questionnaire (preferences.interested_roles).
export function RoleMatchCard({ match, role, threshold, closest = false, goal = false }) {
  const stage = role?.career_stage;
  const matched = match.matched.slice(0, 4);
  const gaps = match.gaps.slice(0, closest ? 4 : 3);

  return (
    <article className={`flex flex-col rounded-xl border bg-glass p-5 shadow-sm md:p-6 ${goal ? "border-accent ring-1 ring-accent/30" : "border-border"}`} aria-labelledby={`role-${match.role_id}`}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id={`role-${match.role_id}`} className="text-h3 font-semibold text-text">
            {match.title_th}
          </h2>
          {role?.title_en && <p className="font-[family-name:var(--font-latin-first)] text-small text-text-muted">{role.title_en}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {goal && <GoalBadge />}
          <StageBadge stage={stage} />
        </div>
      </header>

      <div className="mt-4">
        <MatchMeter pct={match.match_pct} threshold={threshold} />
      </div>
      <div className="mt-2">
        <ExperienceNote stage={stage} />
      </div>

      <div className={`mt-5 grid gap-4 ${closest ? "" : "sm:grid-cols-2"}`}>
        {closest && gaps.length > 0 && (
          <section>
            <h3 className="mb-2 text-tiny font-semibold text-text-muted">สิ่งที่ยังขาด</h3>
            <ul className="space-y-1.5">
              {gaps.map((g) => (
                <li key={g.gap_id}>
                  <GapLabel gap={g} />
                </li>
              ))}
            </ul>
          </section>
        )}
        <section>
          <h3 className="mb-2 text-tiny font-semibold text-text-muted">ทักษะที่ตรง</h3>
          {matched.length ? (
            <ul className="space-y-1.5">
              {matched.map((m) => (
                <MatchedSkill key={m.skill_id} skill={m} />
              ))}
            </ul>
          ) : (
            <p className="text-small text-text-muted">ยังไม่มี</p>
          )}
        </section>
        {!closest && (
          <section>
            <h3 className="mb-2 text-tiny font-semibold text-text-muted">ควรเติม</h3>
            {gaps.length ? (
              <ul className="space-y-1.5">
                {gaps.map((g) => (
                  <li key={g.gap_id}>
                    <GapLabel gap={g} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-small text-text-muted">ครบทุกทักษะที่ต้องมี</p>
            )}
          </section>
        )}
      </div>

      {match.explanations_stale ? (
        <p className="mt-5 rounded-md bg-bg px-3 py-2 text-small text-text-muted">
          คำอธิบายยังเป็นของโปรไฟล์เดิม · กด “อัปเดตคำอธิบาย” ด้านบนเพื่อดูก้าวถัดไปล่าสุด
        </p>
      ) : (
        <>
          {match.reason_th && (
            <p className="mt-5 text-small text-text">
              {match.reason_th}
              <Cite ids={match.matched.slice(0, 2).flatMap((m) => m.evidence_ids.slice(0, 1))} />
            </p>
          )}
          {match.next_steps.length > 0 && (
            <section className="mt-4">
              <h3 className="mb-2 text-tiny font-semibold text-text-muted">ก้าวถัดไป</h3>
              <NextSteps steps={match.next_steps} gaps={match.gaps} limit={5} />
            </section>
          )}
        </>
      )}

      <div className="mt-auto pt-5">
        <Link
          href={`/roles/${match.role_id}`}
          className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-small font-semibold text-on-primary shadow-sm hover:bg-primary-hover"
        >
          ดูรายละเอียด
          <span className="sr-only">{match.title_th}</span>
          <ArrowRight className="size-4" strokeWidth={2} aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}
