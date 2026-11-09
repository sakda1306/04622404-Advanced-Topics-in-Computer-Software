"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, Route, Star } from "lucide-react";
import { data } from "@/lib/data";
import { Meter } from "@/components/charts/meter";

// "สายงานที่คุณเลือกไว้": the roles the user picked in the questionnaire
// (preferences.interested_roles), pinned above the results and shown even when
// they score below the threshold. The match list only holds the top 5, so a
// picked role outside it is read from GET /api/roles/{role_id}.

/**
 * Resolves the user's picked roles to {role_id, title_th, title_en, match, inTop}.
 * A role whose detail call fails keeps match: null and is still listed.
 */
export async function loadGoalRoles(profile, matches, catalogue) {
  const ids = (profile?.preferences?.interested_roles ?? []).filter((id) => catalogue[id]);
  const top = Object.fromEntries(matches.roles.map((m) => [m.role_id, m]));
  return Promise.all(
    [...new Set(ids)].map(async (id) => {
      const base = { role_id: id, title_th: catalogue[id].title_th, title_en: catalogue[id].title_en, inTop: Boolean(top[id]) };
      if (top[id]) return { ...base, match: top[id] };
      const match = await data.role(id).then(
        (r) => r.match,
        () => null,
      );
      return { ...base, match };
    }),
  );
}

const hardGaps = (match) => (match?.gaps ?? []).filter((g) => g.kind !== "soft_skill");

function GoalStatus({ goal, threshold }) {
  const { match } = goal;
  if (!match) return <p className="text-small text-text-muted">ยังคำนวณคะแนนสายงานนี้ไม่ได้ ลองใหม่ภายหลัง</p>;
  if (goal.inTop) {
    return (
      <p className="flex items-start gap-1.5 text-small font-medium text-success">
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" strokeWidth={2} aria-hidden="true" />
        ตรงกับเป้าหมาย! อยู่ในสายงานที่เหมาะที่สุดของคุณ
      </p>
    );
  }
  const missing = hardGaps(match).length;
  if (missing === 0) {
    return (
      <p className="flex items-start gap-1.5 text-small text-text">
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" strokeWidth={2} aria-hidden="true" />
        มีทักษะที่ต้องมีครบแล้ว{match.match_pct < threshold ? " · เติมทักษะที่ควรมีเพื่อเพิ่มคะแนน" : ""}
      </p>
    );
  }
  return (
    <Link
      href={`/roles/${goal.role_id}#gaps`}
      className="group flex items-start gap-1.5 rounded-sm text-small font-semibold text-accent hover:underline"
    >
      <Route className="mt-0.5 size-4 shrink-0" strokeWidth={2} aria-hidden="true" />
      <span>
        ขาดอีก {missing} ทักษะ เพื่อไปถึง {goal.title_th}
        <ArrowRight className="ml-1 inline size-3.5 transition-transform duration-150 group-hover:translate-x-0.5" strokeWidth={2} aria-hidden="true" />
      </span>
    </Link>
  );
}

export function GoalRoles({ goals, threshold }) {
  if (!goals?.length) return null;
  return (
    <section aria-labelledby="goal-roles" className="rounded-xl border border-accent/40 bg-primary-subtle/40 p-5 md:p-6 backdrop-blur-md">
      <header className="flex flex-wrap items-start gap-3">
        <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-surface text-accent shadow-sm">
          <Star className="size-5 fill-current" strokeWidth={1.75} aria-hidden="true" />
        </span>
        <div>
          <h2 id="goal-roles" className="text-h3 font-semibold text-text">
            สายงานที่คุณเลือกไว้
          </h2>
          <p className="mt-0.5 text-small text-text-muted">จากแบบสอบถาม · แสดงเสมอ แม้คะแนนยังไม่ถึงเกณฑ์ {threshold}%</p>
        </div>
      </header>

      <ul className="mt-5 grid gap-3 sm:grid-cols-2">
        {goals.map((g) => (
          <li key={g.role_id} className="flex flex-col gap-3 rounded-lg border border-border bg-glass p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Link href={`/roles/${g.role_id}`} className="font-semibold text-text hover:text-accent hover:underline">
                  {g.title_th}
                </Link>
                {g.title_en && <p className="font-[family-name:var(--font-latin-first)] text-tiny text-text-muted">{g.title_en}</p>}
              </div>
              {g.match && (
                <span className="tabular shrink-0 font-[family-name:var(--font-latin-first)] text-h3 font-semibold text-accent">
                  {g.match.match_pct}%
                </span>
              )}
            </div>
            {g.match && <Meter value={g.match.match_pct} />}
            <GoalStatus goal={g} threshold={threshold} />
          </li>
        ))}
      </ul>
    </section>
  );
}
