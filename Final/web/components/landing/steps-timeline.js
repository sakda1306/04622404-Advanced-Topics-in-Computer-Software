"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Compass, FilePlus2, Route, UserRound } from "lucide-react";
import { useReducedMotion } from "@/lib/use-motion";

// Landing "4 ขั้นตอน" as a timeline on a curved line. The line fills up to the
// active step. While the section is on screen it steps through 1 → 4 by itself;
// hovering, focusing or tapping a step takes over. With reduced motion there is
// no auto-play and the line is drawn in full.

const STEPS = [
  {
    title: "เพิ่มข้อมูล",
    Icon: FilePlus2,
    stats: [{ label: "ช่องทาง", value: "CV · แบบสอบถาม" }],
    checks: ["เริ่มจาก CV หรือแบบสอบถามก็ได้", "แชทช่วยเติมส่วนที่ยังขาด"],
  },
  {
    title: "ดูโปรไฟล์",
    Icon: UserRound,
    stats: [
      { label: "หมวด", value: "5" },
      { label: "ทุกทักษะมี", value: "ที่มา" },
    ],
    checks: ["แก้ไขผ่านแชทได้", "ลบทักษะที่ไม่ใช่ได้ทันที"],
  },
  {
    title: "เลือกสายงาน",
    Icon: Compass,
    stats: [
      { label: "สายงานที่แนะนำ", value: "5" },
      { label: "คะแนนแยก", value: "4 ส่วน" },
    ],
    checks: ["อธิบายที่มาของคะแนน", "ไม่ใช่การรับประกันการได้งาน"],
  },
  {
    title: "วางแผนต่อ",
    Icon: Route,
    stats: [
      { label: "ขั้นตอนถัดไป", value: "≤ 5" },
      { label: "ข้อมูลเงินเดือน", value: "กรุงเทพฯ" },
    ],
    checks: ["เรียงตามความสำคัญ", "บอกแหล่งที่มาและวันที่"],
  },
];

// Wave geometry, drawn in real pixels for the measured width (a stretched SVG
// would distort the curve and break the dash fill). The nodes sit at the centre
// of each of the four columns and alternate low and high, joined by S-curves
// with flat tangents.
const H = 160;
const NODE_Y = [112, 48, 112, 48];
const AUTO_MS = 2600;

function geometry(width) {
  const nodes = NODE_Y.map((y, i) => ({ x: ((i + 0.5) / NODE_Y.length) * width, y }));
  const pull = width / 9;
  const curve = (a, b) => `M${a.x} ${a.y} C ${a.x + pull} ${a.y}, ${b.x - pull} ${b.y}, ${b.x} ${b.y}`;
  const [first, last] = [nodes[0], nodes[nodes.length - 1]];
  return {
    nodes,
    leadIn: `M0 ${first.y + 20} C ${first.x * 0.4} ${first.y + 20}, ${first.x * 0.6} ${first.y}, ${first.x} ${first.y}`,
    leadOut: `M${last.x} ${last.y} C ${last.x + (width - last.x) * 0.4} ${last.y}, ${last.x + (width - last.x) * 0.6} ${last.y - 20}, ${width} ${last.y - 20}`,
    segments: nodes.slice(0, -1).map((n, i) => curve(n, nodes[i + 1])),
  };
}

function Stats({ stats }) {
  return (
    <dl className="mt-3 flex gap-6 border-b border-border pb-3">
      {stats.map((s) => (
        <div key={s.label}>
          <dt className="text-tiny text-text-muted">{s.label}</dt>
          <dd className="mt-0.5 text-h3 font-semibold text-text">{s.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Checks({ checks }) {
  return (
    <ul className="mt-3 space-y-2">
      {checks.map((c) => (
        <li key={c} className="flex items-start gap-2 text-small text-text-muted">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" strokeWidth={1.5} aria-hidden="true" />
          {c}
        </li>
      ))}
    </ul>
  );
}

function Node({ step, index, active, reached, onSelect, className = "", style }) {
  const { Icon, title } = step;
  return (
    <button
      type="button"
      onClick={() => onSelect(index)}
      onFocus={() => onSelect(index)}
      aria-label={`ขั้นที่ ${index + 1}: ${title}`}
      aria-current={active ? "step" : undefined}
      className={`timeline-node inline-flex size-12 items-center justify-center rounded-full border-2 transition-[background-color,border-color,transform] duration-300 ease-out focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary ${
        reached ? "border-primary bg-primary text-on-primary" : "border-border bg-surface text-text-muted"
      } ${active ? "timeline-node-active scale-110" : ""} ${className}`}
      style={style}
    >
      <Icon className="size-5" strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}

function Wave({ width, shown, active, onSelect }) {
  const { nodes, leadIn, leadOut, segments } = geometry(width);
  const line = { fill: "none", strokeWidth: 3, strokeLinecap: "round" };
  return (
    <>
      <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} className="absolute inset-0" aria-hidden="true">
        {[leadIn, ...segments, leadOut].map((d) => (
          <path key={d} d={d} stroke="var(--color-border)" {...line} />
        ))}
        <path d={leadIn} stroke="var(--color-primary)" {...line} />
        {segments.map((d, i) => (
          <path
            key={d}
            d={d}
            pathLength="1"
            stroke="var(--color-primary)"
            strokeDasharray="1 1"
            strokeDashoffset={i < shown ? 0 : 1}
            className="transition-[stroke-dashoffset] duration-700 ease-out"
            {...line}
          />
        ))}
      </svg>
      {STEPS.map((s, i) => (
        <Node
          key={s.title}
          step={s}
          index={i}
          active={i === active}
          reached={i <= shown}
          onSelect={onSelect}
          className="absolute -translate-x-1/2 -translate-y-1/2"
          style={{ left: nodes[i].x, top: nodes[i].y }}
        />
      ))}
    </>
  );
}

export function StepsTimeline() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);
  const [taken, setTaken] = useState(false); // the user took over, so auto-play stops
  const [visible, setVisible] = useState(false);
  const ref = useRef(null);
  const waveRef = useRef(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = waveRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (reduced || taken || !visible) return undefined;
    const t = setInterval(() => setActive((i) => (i + 1) % STEPS.length), AUTO_MS);
    return () => clearInterval(t);
  }, [reduced, taken, visible]);

  const select = (i) => {
    setTaken(true);
    setActive(i);
  };
  // With reduced motion every step reads as reached and the line is full.
  const shown = reduced ? STEPS.length - 1 : active;

  return (
    <div ref={ref} className="mt-12">
      {/* md and up: horizontal wave with the cards under their nodes */}
      <div ref={waveRef} className="relative hidden md:block" style={{ height: H }}>
        {width > 0 && <Wave width={width} shown={shown} active={reduced ? -1 : active} onSelect={select} />}
      </div>

      <ol className="grid gap-5 md:mt-4 md:grid-cols-4">
        {STEPS.map((s, i) => {
          const isActive = !reduced && i === active;
          return (
            <li
              key={s.title}
              onMouseEnter={() => select(i)}
              onClick={() => select(i)}
              className={`relative flex gap-4 rounded-xl border bg-surface p-5 shadow-sm transition-[border-color,box-shadow,transform] duration-300 ease-out md:block ${
                isActive ? "border-primary shadow-md md:-translate-y-1" : "border-border"
              }`}
            >
              {/* below md: a straight rail with the node on the left */}
              <div className="relative flex flex-col items-center md:hidden">
                <Node step={s} index={i} active={isActive} reached={i <= shown} onSelect={select} className="relative" />
                {i < STEPS.length - 1 && (
                  <span className="absolute top-12 -bottom-10 w-0.5 bg-border" aria-hidden="true">
                    <span
                      className="block w-full bg-primary transition-[height] duration-700 ease-out"
                      style={{ height: i < shown ? "100%" : "0%" }}
                    />
                  </span>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-[family-name:var(--font-latin-first)] text-tiny text-text-muted tabular">
                  ขั้นที่ {String(i + 1).padStart(2, "0")}
                </p>
                <h3 className="mt-0.5 text-h3 font-semibold text-text">{s.title}</h3>
                <Stats stats={s.stats} />
                <Checks checks={s.checks} />
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
