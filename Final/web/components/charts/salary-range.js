"use client";

import { useMemo } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { baht, bahtRange, dateTh } from "@/lib/format";
import { CHART_MOTION, useReducedMotion } from "@/lib/use-motion";
import { ChartCard, LegendItem, TooltipBox } from "./chart-card";

const COLOR = {
  advertised: "var(--color-chart-you)",
  reference: "var(--color-chart-ref)",
  baseline: "var(--color-text)",
};

// A range is a bar from min to max; the single official figure is a diamond.
function RangeShape(props) {
  const { x, y, width, height, payload } = props;
  const fill = COLOR[payload.key];
  if (payload.key === "baseline") {
    const cx = x + width / 2;
    const cy = y + height / 2;
    const r = 7;
    return <path d={`M${cx} ${cy - r} L${cx + r} ${cy} L${cx} ${cy + r} L${cx - r} ${cy} Z`} fill={fill} stroke="var(--color-surface)" strokeWidth={2} />;
  }
  return <rect x={x} y={y + height * 0.2} width={Math.max(width, 2)} height={height * 0.6} rx={4} fill={fill} />;
}

function rangeText(d) {
  return d.key === "baseline" ? baht(d.value) : bahtRange(d.min, d.max);
}

function SalaryTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <TooltipBox
      title={d.label}
      rows={[
        { color: COLOR[d.key], label: "ช่วง", value: rangeText(d) },
        { label: "แหล่งที่มา", value: d.source },
        { label: "รายละเอียด", value: d.detail },
        { label: "ข้อมูล ณ", value: dateTh(d.asOf) },
      ]}
    />
  );
}

/**
 * Salary layers on one ฿ axis (PRD FR-21): advertised and reference ranges as
 * bars, the official industry figure as one point. Never a single "true" salary.
 */
export function SalaryRange({ layers, roleTitle }) {
  const reduced = useReducedMotion();
  const data = useMemo(() => layers.map((l) => ({ ...l, range: l.key === "baseline" ? [l.value, l.value] : [l.min, l.max] })), [layers]);
  const lo = Math.floor(Math.min(...data.map((d) => d.range[0])) / 5000) * 5000 - 5000;
  const hi = Math.ceil(Math.max(...data.map((d) => d.range[1])) / 5000) * 5000 + 5000;

  return (
    <ChartCard
      title="ช่วงเงินเดือน"
      description={`${roleTitle} · ฐานเงินเดือนต่อเดือน · ข้อมูลกรุงเทพฯ`}
      legend={
        <div className="flex flex-wrap gap-4">
          <LegendItem color={COLOR.advertised}>ที่ประกาศในงาน</LegendItem>
          <LegendItem color={COLOR.reference}>ตารางอ้างอิง</LegendItem>
          <span className="inline-flex items-center gap-2 text-small text-text">
            <svg width="14" height="14" aria-hidden="true">
              <path d="M7 1 L13 7 L7 13 L1 7 Z" fill={COLOR.baseline} />
            </svg>
            ค่าจ้างอุตสาหกรรม IT (ตัวเลขเดียว)
          </span>
        </div>
      }
      table={{
        columns: ["ชั้นข้อมูล", "ช่วง / ค่า", "แหล่งที่มา", "ข้อมูล ณ"],
        rows: layers.map((l) => [l.label, rangeText(l), l.source, dateTh(l.asOf)]),
      }}
      note="แสดงเป็นช่วงเสมอ ไม่มีตัวเลขเดียวที่เป็นเงินเดือนจริง ตารางอ้างอิงจัดทำโดยทีมผู้พัฒนา"
    >
      <div className="h-[200px] w-full" role="img" aria-label="ช่วงเงินเดือนจาก 3 แหล่ง">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 0 }} barCategoryGap={8}>
            <XAxis
              type="number"
              domain={[lo, hi]}
              tickCount={5}
              tickFormatter={(v) => `฿${Math.round(v / 1000)}k`}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--color-text-muted)", fontSize: 12 }}
            />
            <YAxis type="category" dataKey="label" width={150} axisLine={false} tickLine={false} tick={{ fill: "var(--color-text)", fontSize: 13 }} />
            <Tooltip content={<SalaryTooltip />} cursor={{ fill: "var(--color-bg)", opacity: 0.6 }} />
            <Bar dataKey="range" shape={<RangeShape />} isAnimationActive={!reduced} animationDuration={CHART_MOTION.duration} animationEasing={CHART_MOTION.easing}>
              {data.map((d) => (
                <Cell key={d.key} fill={COLOR[d.key]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-3 grid gap-1 text-small sm:grid-cols-3">
        {layers.map((l) => (
          <li key={l.key} className="tabular text-text">
            <span className="font-semibold">{rangeText(l)}</span>
            <span className="block text-tiny text-text-muted">
              {l.source} · {dateTh(l.asOf)}
            </span>
          </li>
        ))}
      </ul>
    </ChartCard>
  );
}
