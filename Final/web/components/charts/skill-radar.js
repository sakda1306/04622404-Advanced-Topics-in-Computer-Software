"use client";

import { useMemo } from "react";
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import { CHART_MOTION, useReducedMotion } from "@/lib/use-motion";
import { ChartCard, LegendItem, TooltipBox } from "./chart-card";

const LEVEL = ["ยังไม่มี", "เริ่มต้น", "ใช้งานได้", "คล่อง", "เชี่ยวชาญ"];
const YOU = "var(--color-chart-you)";
const REF = "var(--color-chart-ref)";

function status(s) {
  if (s.userLevel === 0) return "ยังไม่มี";
  return s.userLevel >= s.minLevel ? "ผ่าน" : "ต่ำกว่าระดับ";
}

// Axis label: long any-of groups wrap at " / " so they stay inside the card.
function AxisTick({ x, y, cy, payload, textAnchor }) {
  const parts = String(payload.value).split(" / ");
  const lines = parts.length > 2 ? [parts.slice(0, 2).join(" / "), parts.slice(2).join(" / ")] : [parts.join(" / ")];
  // Labels above the centre grow upwards, labels below grow downwards.
  const above = cy !== undefined ? y < cy - 4 : false;
  const firstDy = above ? -(lines.length - 1) * 15 - 2 : 8;
  return (
    <text x={x} y={y} textAnchor={textAnchor} fill="var(--color-text-muted)" fontSize={12}>
      {lines.map((line, i) => (
        <tspan key={line} x={x} dy={i === 0 ? firstDy : 15}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

function RadarTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const s = payload[0].payload;
  return (
    <TooltipBox
      title={s.label}
      rows={[
        { color: YOU, label: "ระดับของคุณ", value: LEVEL[s.userLevel] },
        { color: REF, dashed: true, label: "สายงานต้องการ", value: LEVEL[s.minLevel] },
        { label: "สถานะ", value: status(s) },
      ]}
    />
  );
}

/**
 * Skill overlap radar (DesignSystem charts plan): the role's required level as a
 * dashed grey outline, the user's level as a teal fill, on a fixed 0..4 scale.
 * One axis per required skill or any-of group, always in the role's order.
 */
export function SkillRadar({ roleTitle, skills }) {
  const reduced = useReducedMotion();
  const data = useMemo(() => skills.map((s) => ({ ...s, you: s.userLevel, need: s.minLevel })), [skills]);

  return (
    <ChartCard
      title={`ทักษะของคุณเทียบกับ ${roleTitle}`}
      description="ระดับ 0 ยังไม่มี · 1 เริ่มต้น · 2 ใช้งานได้ · 3 คล่อง · 4 เชี่ยวชาญ"
      legend={
        <div className="flex flex-wrap gap-4">
          <LegendItem color={YOU}>ระดับของคุณ</LegendItem>
          <LegendItem color={REF} dashed>
            ระดับที่สายงานต้องการ
          </LegendItem>
        </div>
      }
      table={{
        columns: ["ทักษะ", "สายงานต้องการ", "ระดับของคุณ", "สถานะ"],
        rows: skills.map((s) => [s.label, LEVEL[s.minLevel], LEVEL[s.userLevel], status(s)]),
      }}
      note="กราฟนี้เป็นภาพรวม รายละเอียดแต่ละทักษะและน้ำหนักอยู่ในรายการทักษะที่ต้องมี"
    >
      <div className="h-[340px] w-full" role="img" aria-label={`กราฟเรดาร์ทักษะ ${skills.length} ด้าน เทียบกับสายงาน ${roleTitle}`}>
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="68%" margin={{ top: 16, right: 40, bottom: 16, left: 40 }}>
            <PolarGrid stroke="var(--color-border)" />
            <PolarAngleAxis dataKey="label" tick={<AxisTick />} />
            <PolarRadiusAxis domain={[0, 4]} tickCount={5} angle={90} axisLine={false} tick={{ fill: "var(--color-text-muted)", fontSize: 10 }} />
            <Radar
              name="สายงานต้องการ"
              dataKey="need"
              stroke={REF}
              strokeWidth={2}
              strokeDasharray="5 4"
              fill="none"
              isAnimationActive={!reduced}
              animationDuration={CHART_MOTION.duration}
              animationEasing={CHART_MOTION.easing}
            />
            <Radar
              name="ระดับของคุณ"
              dataKey="you"
              stroke={YOU}
              strokeWidth={2}
              fill={YOU}
              fillOpacity={0.22}
              dot={{ r: 4, fill: YOU, stroke: "var(--color-surface)", strokeWidth: 2 }}
              activeDot={{ r: 6 }}
              isAnimationActive={!reduced}
              animationBegin={150}
              animationDuration={CHART_MOTION.duration}
              animationEasing={CHART_MOTION.easing}
            />
            <Tooltip content={<RadarTooltip />} cursor={false} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
