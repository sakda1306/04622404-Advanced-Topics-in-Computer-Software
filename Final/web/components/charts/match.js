"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CHART_MOTION, useReducedMotion } from "@/lib/use-motion";
import { ChartCard, LegendItem, TooltipBox } from "./chart-card";
import { HeroNumber, Meter } from "./meter";

const YOU = "var(--color-chart-you)";
const one = (n) => n.toFixed(1);

/** Match % headline: big number + meter + the required disclaimer (DesignSystem.md 5). */
export function MatchSummary({ roleTitle, matchPct, threshold = 60 }) {
  const passes = matchPct >= threshold;
  return (
    <ChartCard title={`ความตรงกับสายงาน ${roleTitle}`} description={`แสดงสายงานที่ได้ตั้งแต่ ${threshold}% ขึ้นไป`}>
      <div className="flex items-end gap-4">
        <HeroNumber value={matchPct} className="text-[56px]" />
        <span className={`mb-2 rounded-full px-3 py-0.5 text-tiny font-medium ${passes ? "bg-primary-subtle text-text" : "border border-warning text-warning"}`}>
          {passes ? "✓ ผ่านเกณฑ์" : "! ต่ำกว่าเกณฑ์"}
        </span>
      </div>
      <div className="mt-4">
        <Meter value={matchPct} size="lg" />
      </div>
      <p className="mt-3 text-tiny text-text-muted">คำนวณจากทักษะที่ตรงกับสายงาน ไม่ใช่การรับประกันการได้งาน</p>
    </ChartCard>
  );
}

/** Completeness meter for the intake sidebar. */
export function CompletenessSummary({ value, threshold = 65 }) {
  return (
    <ChartCard title="ความครบถ้วนของโปรไฟล์" description={`สร้างโปรไฟล์ได้เมื่อถึง ${threshold}% และข้อมูลที่จำเป็นครบ`}>
      <div className="flex items-end gap-3">
        <HeroNumber value={value} className="text-[48px]" />
      </div>
      <div className="mt-4">
        <Meter value={value} size="lg" />
      </div>
      <p className="mt-3 text-small text-text-muted">อีก {threshold - value}% ก็สร้างโปรไฟล์ได้ ลองตอบแบบสอบถามหมวดเป้าหมาย</p>
    </ChartCard>
  );
}

function BreakdownTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <TooltipBox
      title={d.label}
      rows={[
        { color: YOU, label: "ได้", value: `${one(d.earned)} คะแนน` },
        { label: "เต็ม", value: `${d.max} คะแนน` },
        { label: "ที่มา", value: d.detail },
      ]}
    />
  );
}

/**
 * Why the score is what it is: points earned out of each part's maximum on one
 * shared scale, so it is clear that required skills carry most of the score.
 */
export function MatchBreakdown({ parts, matchPct }) {
  const reduced = useReducedMotion();
  // Stable data: Recharts restarts its animation whenever the data array changes.
  const data = useMemo(() => parts.map((p) => ({ ...p, rest: p.max - p.earned, text: `${one(p.earned)} / ${p.max}` })), [parts]);

  return (
    <ChartCard
      title="ที่มาของคะแนน"
      description={`คะแนนรวม ${matchPct} จาก 100 แยกตาม 4 ส่วน`}
      legend={
        <div className="flex flex-wrap gap-4">
          <LegendItem color={YOU}>คะแนนที่ได้</LegendItem>
          <LegendItem color="var(--color-border)">คะแนนเต็มของส่วนนั้น</LegendItem>
        </div>
      }
      table={{
        columns: ["ส่วน", "ได้", "เต็ม", "ที่มา"],
        rows: parts.map((p) => [p.label, one(p.earned), p.max, p.detail]),
      }}
    >
      <div className="h-[200px] w-full" role="img" aria-label={`คะแนนรวม ${matchPct} แยกเป็น 4 ส่วน`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 84, bottom: 0, left: 0 }} barCategoryGap={10}>
            <XAxis type="number" domain={[0, 70]} hide />
            <YAxis type="category" dataKey="label" width={180} axisLine={false} tickLine={false} tick={{ fill: "var(--color-text)", fontSize: 13 }} />
            <Tooltip content={<BreakdownTooltip />} cursor={{ fill: "var(--color-bg)", opacity: 0.6 }} />
            <Bar dataKey="earned" stackId="a" fill={YOU} radius={[4, 0, 0, 4]} isAnimationActive={!reduced} animationDuration={CHART_MOTION.duration} animationEasing={CHART_MOTION.easing} />
            <Bar dataKey="rest" stackId="a" fill="var(--color-border)" radius={[0, 4, 4, 0]} isAnimationActive={!reduced} animationDuration={CHART_MOTION.duration} animationEasing={CHART_MOTION.easing}>
              <LabelList dataKey="text" position="right" fill="var(--color-text-muted)" fontSize={12} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}

function TrendTooltip({ active, payload, postings }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const rows = [{ color: YOU, label: "พบในประกาศ", value: `${d.count} จาก ${postings}` }];
  if (d.owned) rows.push({ label: "คุณมีทักษะนี้แล้ว", value: "✓" });
  return <TooltipBox title={d.name} rows={rows} />;
}

// Axis labels: the column is as wide as the longest name (up to LABEL_MAX), and a
// longer name wraps onto a second line, then ends in "…". The full name is always
// in the tooltip and the table view.
const LABEL_FONT = 13;
const LABEL_LINE = 16;
const LABEL_MIN = 64;
const LABEL_MAX = 180;
const CHECK_SPACE = 18;

// Thai has no spaces between words, so lines break at word boundaries found by
// Intl.Segmenter (falling back to whole characters), never inside a character
// with its vowel or tone marks.
const segmenter = (granularity) =>
  typeof Intl !== "undefined" && Intl.Segmenter ? new Intl.Segmenter("th", { granularity }) : null;
const WORDS = segmenter("word");
const GRAPHEMES = segmenter("grapheme");
const pieces = (text, seg) => (seg ? [...seg.segment(text)].map((p) => p.segment) : [...text]);

function wrapLabel(text, measure, max, maxLines = 2) {
  const words = pieces(text, WORDS);
  const lines = [];
  let line = "";
  let i = 0;
  for (; i < words.length; i += 1) {
    const word = words[i];
    if (measure(line + word) <= max) {
      line += word;
      continue;
    }
    if (line.trim()) {
      // An opening bracket goes down with the word it opens.
      const open = line.trimEnd().match(/[([]$/);
      const head = open ? line.trimEnd().slice(0, -1) : line;
      lines.push(head.trim());
      line = (open ? open[0] : "") + word.trimStart();
    } else {
      // One word wider than the line: split it between characters; the rest is
      // handled as the next word.
      const chars = pieces(word, GRAPHEMES);
      let n = 1;
      while (n < chars.length && measure(chars.slice(0, n + 1).join("")) <= max) n += 1;
      lines.push(chars.slice(0, n).join(""));
      line = "";
      if (n < chars.length) words.splice(i + 1, 0, chars.slice(n).join(""));
    }
    if (lines.length === maxLines) break;
  }
  if (lines.length < maxLines) {
    if (line.trim()) lines.push(line.trim());
    return lines;
  }
  // Out of lines with text left over: end the last line in "…".
  const leftover = line + words.slice(i + 1).join("");
  if (leftover.trim() || measure(lines[maxLines - 1]) > max) {
    const chars = pieces(lines[maxLines - 1], GRAPHEMES);
    while (chars.length > 1 && measure(`${chars.join("")}…`) > max) chars.pop();
    lines[maxLines - 1] = `${chars.join("").trimEnd()}…`;
  }
  return lines;
}

/** Measures label widths with a canvas once the page has fonts; a rough estimate before that. */
function useLabelLayout(names) {
  const [measure, setMeasure] = useState(() => (t) => t.length * 7.5);
  // Owned skills are drawn bold, which is wider; their check sits by the bold width.
  const [measureBold, setMeasureBold] = useState(() => (t) => t.length * 8);
  useEffect(() => {
    const ctx = document.createElement("canvas").getContext("2d");
    if (!ctx) return;
    const family = getComputedStyle(document.body).fontFamily;
    const update = () => {
      ctx.font = `${LABEL_FONT}px ${family}`;
      const regular = (t) => {
        ctx.font = `${LABEL_FONT}px ${family}`;
        return ctx.measureText(t).width;
      };
      const bold = (t) => {
        ctx.font = `600 ${LABEL_FONT}px ${family}`;
        return ctx.measureText(t).width;
      };
      setMeasure(() => regular);
      setMeasureBold(() => bold);
    };
    update();
    document.fonts?.ready.then(update);
  }, []);
  return useMemo(() => {
    const widest = Math.max(0, ...names.map(measure));
    const textMax = Math.min(LABEL_MAX, widest);
    const lines = Object.fromEntries(names.map((n) => [n, wrapLabel(n, measure, textMax)]));
    const textWidth = Object.fromEntries(names.map((n) => [n, Math.max(...lines[n].map(measureBold))]));
    const twoLines = Object.values(lines).some((l) => l.length > 1);
    return { width: Math.max(LABEL_MIN, Math.ceil(textMax) + CHECK_SPACE + 8), lines, textWidth, twoLines };
  }, [names, measure, measureBold]);
}

function SkillTick({ x, y, payload, layout, ownedNames }) {
  const lines = layout.lines[payload.value] ?? [payload.value];
  const owned = ownedNames.has(payload.value);
  const top = -((lines.length - 1) * LABEL_LINE) / 2;
  return (
    <g transform={`translate(${x},${y})`}>
      {owned && (
        // Just before the label (labels are right-aligned, so a short name keeps its check close).
        <path
          d="M 0 0 l 3.5 3.5 l 7 -7"
          transform={`translate(${-6 - (layout.textWidth[payload.value] ?? 0) - 16},0)`}
          fill="none"
          stroke={YOU}
          strokeWidth="2.25"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
      <text x={-6} y={top} textAnchor="end" dominantBaseline="central" fill="var(--color-text)" fontSize={LABEL_FONT} fontWeight={owned ? 600 : 400}>
        {lines.map((line, i) => (
          <tspan key={i} x={-6} dy={i === 0 ? 0 : LABEL_LINE}>
            {line}
          </tspan>
        ))}
      </text>
    </g>
  );
}

/**
 * Market demand: skills most often asked for in the cached postings, sorted.
 * `owned` (optional) is a Set of skill_ids the user has; those rows get a check.
 */
export function TrendingSkills({ data, roleTitle, owned }) {
  const reduced = useReducedMotion();
  // Keyed on the ids, not the Set, so a new Set with the same skills does not replay the chart.
  const ownedKey = owned ? [...owned].sort().join("|") : "";
  const skills = useMemo(() => {
    const have = new Set(ownedKey ? ownedKey.split("|") : []);
    return [...data.skills].sort((a, b) => b.count - a.count).map((s) => ({ ...s, owned: Boolean(s.skill_id && have.has(s.skill_id)) }));
  }, [data.skills, ownedKey]);
  const names = useMemo(() => skills.map((s) => s.name), [skills]);
  const ownedNames = useMemo(() => new Set(skills.filter((s) => s.owned).map((s) => s.name)), [skills]);
  const layout = useLabelLayout(names);
  const rowHeight = layout.twoLines ? 40 : 28;
  const height = Math.max(160, skills.length * rowHeight);
  const ownedCount = ownedNames.size;

  return (
    <ChartCard
      title="ทักษะที่ประกาศงานต้องการบ่อย"
      description={`${roleTitle} · จาก ${data.postings} ประกาศ · ข้อมูลกรุงเทพฯ`}
      table={{
        columns: owned ? ["ทักษะ", "จำนวนประกาศ", "คุณมีแล้ว"] : ["ทักษะ", "จำนวนประกาศ"],
        rows: skills.map((s) => (owned ? [s.name, `${s.count} / ${data.postings}`, s.owned ? "มี" : "–"] : [s.name, `${s.count} / ${data.postings}`])),
      }}
      legend={
        owned && (
          <span className="inline-flex items-center gap-2 text-small text-text">
            <svg width="14" height="10" viewBox="0 0 14 10" aria-hidden="true">
              <path d="M2 5 l3 3 l7 -7" fill="none" stroke={YOU} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            คุณมีทักษะนี้แล้ว · {ownedCount} จาก {skills.length} ทักษะ
          </span>
        )
      }
      note="ข้อมูลประกาศงานรวบรวมจากแหล่งที่ไม่เป็นทางการ อาจไม่ครบถ้วน"
    >
      <div className="w-full" style={{ height }} role="img" aria-label={`ทักษะที่พบบ่อยใน ${data.postings} ประกาศ${owned ? ` · คุณมีแล้ว ${ownedCount} จาก ${skills.length} ทักษะ` : ""}`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={skills} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }} barCategoryGap={6}>
            <XAxis type="number" domain={[0, data.postings]} hide />
            <YAxis
              type="category"
              dataKey="name"
              width={layout.width}
              interval={0}
              axisLine={false}
              tickLine={false}
              tick={<SkillTick layout={layout} ownedNames={ownedNames} />}
            />
            <Tooltip content={<TrendTooltip postings={data.postings} />} cursor={{ fill: "var(--color-bg)", opacity: 0.6 }} />
            <Bar dataKey="count" fill={YOU} radius={[0, 4, 4, 0]} isAnimationActive={!reduced} animationDuration={CHART_MOTION.duration} animationEasing={CHART_MOTION.easing}>
              <LabelList dataKey="count" position="right" fill="var(--color-text-muted)" fontSize={12} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
