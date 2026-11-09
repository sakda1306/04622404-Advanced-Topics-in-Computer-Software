"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dateTh, num } from "@/lib/format";
import { CHART_MOTION, useCountUp, useEntered, useReducedMotion } from "@/lib/use-motion";
import { ChartCard, LegendItem, TooltipBox } from "./chart-card";
import { Meter } from "./meter";

const YOU = "var(--color-chart-you)";
const REF = "var(--color-chart-ref)";

const FORMAT = {
  num: (v) => num(v),
  pct1: (v) => `${v.toFixed(1)}%`,
  sec: (v) => `${v.toFixed(1)} วิ`,
};

/** Admin stat tile: label, counting-up value, and a status line with an icon. */
export function StatTile({ label, value, format = "num", warnAbove, target }) {
  const shown = useCountUp(value);
  const warn = warnAbove !== undefined && value > warnAbove;
  const statusText = target !== undefined ? `เป้าหมาย ไม่เกิน ${target} วิ` : warnAbove !== undefined ? `เตือนเมื่อเกิน ${warnAbove}%` : null;
  const ok = target !== undefined ? value <= target : !warn;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-small text-text-muted">{label}</p>
      <p className="tabular mt-1 text-h1 font-semibold text-text">{FORMAT[format](shown)}</p>
      {statusText && (
        <p className={`mt-1 inline-flex items-center gap-1.5 text-tiny font-medium ${ok ? "text-success" : "text-warning"}`}>
          {ok ? <CheckCircle2 className="size-3.5" strokeWidth={2} aria-hidden="true" /> : <AlertTriangle className="size-3.5" strokeWidth={2} aria-hidden="true" />}
          {statusText}
        </p>
      )}
    </div>
  );
}

/** LLM tokens / requests and Apify runs against their limits; warning from 80%. */
export function UsageMeters({ items }) {
  return (
    <ChartCard
      title="การใช้ AI และข้อมูลตลาดวันนี้"
      description="เทียบกับขีดจำกัดของบัญชี เตือนเมื่อใช้ถึง 80%"
      table={{ columns: ["รายการ", "ใช้ไป", "ขีดจำกัด", "%"], rows: items.map((i) => [i.label, num(i.used), num(i.limit), `${Math.round((i.used / i.limit) * 100)}%`]) }}
    >
      <div className="space-y-5">
        {items.map((i) => (
          <Meter
            key={i.key}
            label={i.label}
            value={i.used}
            max={i.limit}
            warnAt={0.8}
            warnText="ใกล้ถึงขีดจำกัด"
            format={(v, max) => `${num(v)} / ${num(max)}`}
          />
        ))}
      </div>
    </ChartCard>
  );
}

/** Parts of a whole as sorted horizontal bars with the % at the end (no pie). */
export function ShareBars({ title, description, items, labelKey, valueKey = "share" }) {
  const entered = useEntered();
  const sorted = [...items].sort((a, b) => b[valueKey] - a[valueKey]);
  const top = sorted[0]?.[valueKey] || 1;

  return (
    <ChartCard title={title} description={description} table={{ columns: ["รายการ", "สัดส่วน"], rows: sorted.map((i) => [i[labelKey], `${Math.round(i[valueKey] * 100)}%`]) }}>
      <ul className="space-y-2.5">
        {sorted.map((i, idx) => (
          <li key={i[labelKey]} className="grid grid-cols-[132px_1fr_44px] items-center gap-3 text-small">
            <code className="truncate text-text">{i[labelKey]}</code>
            <div className="h-2.5 overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full transition-[width] duration-[800ms] ease-out"
                style={{ width: entered ? `${(i[valueKey] / top) * 100}%` : "0%", background: "var(--color-primary)", transitionDelay: `${idx * 50}ms` }}
              />
            </div>
            <span className="tabular text-right text-text-muted">{Math.round(i[valueKey] * 100)}%</span>
          </li>
        ))}
      </ul>
    </ChartCard>
  );
}

function RequestsTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <TooltipBox
      title={dateTh(d.date)}
      rows={[
        { color: YOU, label: "คำขอทั้งหมด", value: num(d.total) },
        { color: REF, dashed: true, label: "คำขอที่ใช้ AI", value: num(d.ai) },
      ]}
    />
  );
}

/** Requests per day, 7 or 30 days. Switching the window redraws with the same motion. */
export function RequestsLine({ byWindow }) {
  const reduced = useReducedMotion();
  const [win, setWin] = useState("7d");
  const data = byWindow[win];
  const short = new Intl.DateTimeFormat("th-TH", { day: "numeric", month: "short" });

  return (
    <ChartCard
      title="คำขอต่อวัน"
      description="ทั้งหมด และเฉพาะคำขอที่เรียก AI"
      legend={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-4">
            <LegendItem color={YOU}>คำขอทั้งหมด</LegendItem>
            <LegendItem color={REF} dashed>
              คำขอที่ใช้ AI
            </LegendItem>
          </div>
          <div role="radiogroup" aria-label="ช่วงเวลา" className="inline-flex rounded-full border border-border bg-bg p-1">
            {[
              ["7d", "7 วัน"],
              ["30d", "30 วัน"],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={win === key}
                onClick={() => setWin(key)}
                className={`min-h-9 rounded-full px-4 text-small font-medium transition-colors duration-150 ${win === key ? "bg-primary text-on-primary" : "text-text-muted hover:text-text"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      }
      table={{ columns: ["วันที่", "คำขอทั้งหมด", "ใช้ AI"], rows: data.map((d) => [dateTh(d.date), num(d.total), num(d.ai)]) }}
    >
      <div className="h-[260px] w-full" role="img" aria-label={`คำขอต่อวัน ${win === "7d" ? "7" : "30"} วันล่าสุด`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart key={win} data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--color-border)" />
            <XAxis
              dataKey="date"
              tickFormatter={(d) => short.format(new Date(d))}
              interval={win === "7d" ? 0 : 4}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--color-text-muted)", fontSize: 12 }}
            />
            <YAxis width={48} axisLine={false} tickLine={false} tickFormatter={num} tick={{ fill: "var(--color-text-muted)", fontSize: 12 }} />
            <Tooltip content={<RequestsTooltip />} cursor={{ stroke: "var(--color-text-muted)", strokeWidth: 1, strokeDasharray: "3 3" }} />
            <Line type="monotone" dataKey="total" stroke={YOU} strokeWidth={2} dot={win === "7d" ? { r: 4, fill: YOU, stroke: "var(--color-surface)", strokeWidth: 2 } : false} activeDot={{ r: 6 }} isAnimationActive={!reduced} animationDuration={CHART_MOTION.duration} animationEasing={CHART_MOTION.easing} />
            <Line type="monotone" dataKey="ai" stroke={REF} strokeWidth={2} strokeDasharray="5 4" dot={false} activeDot={{ r: 5 }} isAnimationActive={!reduced} animationBegin={150} animationDuration={CHART_MOTION.duration} animationEasing={CHART_MOTION.easing} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
