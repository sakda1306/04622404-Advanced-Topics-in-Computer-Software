"use client";

import { useEntered } from "@/lib/use-motion";
import { ChartCard } from "./chart-card";

const YOU = "var(--color-chart-you)";
const REF = "var(--color-chart-ref)";
const pos = (v) => `${(v * 100).toFixed(1)}%`;

/**
 * Work style, you vs the role: one row per trait between its two ends.
 * The role is a dashed grey ring, you are a teal dot, the line between them is
 * the gap. Both markers slide out from the middle on load.
 */
export function WorkStyleDumbbell({ traits, roleTitle }) {
  const entered = useEntered();

  return (
    <ChartCard
      title="รูปแบบการทำงานที่คุณชอบ เทียบกับสายงาน"
      description={roleTitle}
      legend={
        <div className="flex flex-wrap gap-4 text-small text-text">
          <span className="inline-flex items-center gap-2">
            <span className="size-3 rounded-full" style={{ background: YOU }} aria-hidden="true" />
            ความชอบของคุณ
          </span>
          <span className="inline-flex items-center gap-2">
            <span className="size-3 rounded-full border-2 border-dashed" style={{ borderColor: REF }} aria-hidden="true" />
            ลักษณะงานของสายงาน
          </span>
        </div>
      }
      table={{
        columns: ["ด้าน", "คุณ (0–100)", "สายงาน (0–100)", "ห่างกัน"],
        rows: traits.map((t) => [`${t.low} ↔ ${t.high}`, Math.round(t.user * 100), Math.round(t.role * 100), Math.round(Math.abs(t.user - t.role) * 100)]),
      }}
      note="ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ"
    >
      <ul className="space-y-5">
        {traits.map((t, i) => {
          const you = entered ? t.user : 0.5;
          const ref = entered ? t.role : 0.5;
          const left = Math.min(you, ref);
          const width = Math.abs(you - ref);
          const transition = { transitionDelay: `${i * 60}ms` };
          return (
            <li key={t.trait}>
              <div className="mb-1 flex justify-between gap-3 text-tiny text-text-muted">
                <span>{t.low}</span>
                <span className="text-right">{t.high}</span>
              </div>
              <div className="relative h-5" aria-label={`${t.low} ถึง ${t.high}: คุณ ${Math.round(t.user * 100)}, สายงาน ${Math.round(t.role * 100)}`} role="img">
                <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
                <div
                  className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full transition-all duration-[800ms] ease-out"
                  style={{ left: pos(left), width: pos(width), background: YOU, opacity: 0.45, ...transition }}
                />
                <span
                  className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-dashed bg-surface transition-[left] duration-[800ms] ease-out"
                  style={{ left: pos(ref), borderColor: REF, ...transition }}
                />
                <span
                  className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface transition-[left] duration-[800ms] ease-out"
                  style={{ left: pos(you), background: YOU, ...transition }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </ChartCard>
  );
}
