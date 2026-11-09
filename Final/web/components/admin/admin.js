"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  ClipboardList,
  Clock,
  Cpu,
  Database,
  Gauge,
  Info,
  Lightbulb,
  Loader2,
  RefreshCw,
  Route,
  Server,
  ShieldAlert,
  Timer,
  Trash2,
  Users,
  XCircle,
} from "lucide-react";
import { data } from "@/lib/data";
import { usePageReady } from "@/components/motion/page-transition";
import { dateTh, num } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Meter } from "@/components/charts/meter";
import { MiniStat, Note, Pill, ShareStrip, Tile } from "@/components/app/bento";
import { DotGrid } from "@/components/motion/dot-grid";
import { THRESHOLD } from "@/components/intake/completeness-panel";
import { useCountUp, useEntered } from "@/lib/use-motion";
import { Button, ErrorState, LoadingBlock } from "@/components/intake/ui";

// Admin dashboard /admin (PRD FR-40 – FR-45, DesignSystem.md section 4):
// read-only aggregates from GET /api/admin/overview, laid out as a bento grid.
// Header with health chips, the window switch, last updated time and refresh;
// the warning list; then tiles: three KPIs, the cache freshness map (tall), the
// sign-up funnel, AI usage per model, a highlight card, AI Router, average
// completeness gauge, user quota, errors by code, inputs and chat edits, removed
// skills, and the full cache table. Notes under charts are worked out from the
// numbers here, not from AI. Refreshes every 60 s while open. No step indicator,
// no chat, never any user content (FR-42).

// Warning thresholds are api config (ADMIN_WARN_LLM_PCT, ADMIN_WARN_ERROR_PCT);
// the api sends the resulting warnings, and the web colours single values with
// the same numbers, set at build time.
const WARN_LLM_PCT = Number(process.env.NEXT_PUBLIC_ADMIN_WARN_LLM_PCT || 80);
const WARN_ERROR_PCT = Number(process.env.NEXT_PUBLIC_ADMIN_WARN_ERROR_PCT || 5);
const REFRESH_MS = 60000;

const WINDOWS = [
  { id: "today", label: "วันนี้" },
  { id: "7d", label: "7 วัน" },
  { id: "30d", label: "30 วัน" },
];
const PANEL_TH = { health: "สถานะระบบ", llm: "การใช้ AI", quota: "โควตาผู้ใช้", cache: "ข้อมูลตลาดงาน", router: "AI Router" };
const ROLE_TH = { main: "โมเดลหลัก", router: "Router", fallback: "Fallback" };
const PRIORITY_CODES = ["LLM_UNAVAILABLE", "LLM_TIMEOUT", "INTERNAL_ERROR", "RATE_LIMITED"];
const pct = (r) => `${Math.round(r * 100)}%`;
const timeTh = (iso) => new Date(iso).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/* ---------- bento pieces ---------- */

/** Horizontal count bars (errors by code, removed skills): label, bar, number. `stacked` puts the label above the bar (narrow tiles). */
function CountBars({ items, stacked = false }) {
  const top = Math.max(1, ...items.map((i) => i.count));
  if (stacked) {
    return (
      <ul className="space-y-3">
        {items.map((i) => (
          <li key={i.key} className="text-small">
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <span className="truncate text-text">{i.label}</span>
              <span className="tabular shrink-0 text-text-muted">{num(i.count)}</span>
            </div>
            <span className="block h-2 overflow-hidden rounded-full bg-border" aria-hidden="true">
              <span className="block h-full rounded-full bg-[var(--color-series-1)]" style={{ width: `${(i.count / top) * 100}%` }} />
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <ul className="space-y-2.5">
      {items.map((i) => (
        <li key={i.key} className="grid grid-cols-[minmax(0,9.5rem)_1fr_auto] items-center gap-3 text-small">
          <span className={`flex min-w-0 items-center gap-1.5 text-text ${i.mono ? "font-[family-name:var(--font-latin-first)] text-tiny" : ""}`}>
            {i.warn && <AlertTriangle className="size-3.5 shrink-0 text-warning" strokeWidth={2} aria-label="ต้องดู" />}
            <span className="truncate">{i.label}</span>
          </span>
          <span className="h-2 overflow-hidden rounded-full bg-border" aria-hidden="true">
            <span className={`block h-full rounded-full ${i.warn ? "bg-warning" : "bg-[var(--color-series-1)]"}`} style={{ width: `${(i.count / top) * 100}%` }} />
          </span>
          <span className="tabular text-right text-text-muted">{num(i.count)}</span>
        </li>
      ))}
    </ul>
  );
}

function WindowSwitch({ value, onChange }) {
  return (
    <div role="radiogroup" aria-label="ช่วงเวลา" className="inline-flex rounded-full border border-border bg-surface p-1">
      {WINDOWS.map((w) => (
        <button
          key={w.id}
          type="button"
          role="radio"
          aria-checked={value === w.id}
          onClick={() => onChange(w.id)}
          className={`min-h-9 rounded-full px-4 text-small font-medium transition-colors duration-150 ${value === w.id ? "bg-primary text-on-primary shadow-sm" : "text-text-muted hover:text-text"}`}
        >
          {w.label}
        </button>
      ))}
    </div>
  );
}

/** Warning list (FR-44) as a header button: "ทุกอย่างปกติ", or "คำเตือน N" that opens the list. */
function Warnings({ warnings }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => !wrapRef.current?.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  if (!warnings.length) {
    return (
      <p role="status" className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-border bg-surface px-4 text-small text-text">
        <CheckCircle2 className="size-4 text-success" strokeWidth={2} aria-hidden="true" />
        ทุกอย่างปกติ
      </p>
    );
  }
  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="warning-list"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-warning bg-surface px-4 text-small font-semibold text-warning transition-colors duration-150 hover:bg-warning/10"
      >
        <AlertTriangle className="size-4" strokeWidth={2} aria-hidden="true" />
        คำเตือน {warnings.length}
      </button>
      {open && (
        <section id="warning-list" aria-label="คำเตือน" className="absolute right-0 z-40 mt-2 w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-warning/60 bg-bg p-4 shadow-lg">
          <ul className="space-y-2">
            {warnings.map((w, i) => (
              <li key={`${w.code}-${i}`} className="text-small text-text">
                <span className="font-semibold">{PANEL_TH[w.panel] ?? w.panel}:</span> {w.message_th}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/* ---------- tiles ---------- */

// Fit-to-screen layout (globals.css `dash` variant: at least 1280 × 800): a 6 × 3
// grid sized to the window, every tile in its named area; a tile whose content is
// taller than its cell scrolls inside, so the page itself does not scroll.
const AREA = {
  k1: "dash:[grid-area:k1]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  k2: "dash:[grid-area:k2]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  k3: "dash:[grid-area:k3]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  ins: "dash:[grid-area:ins]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  gau: "dash:[grid-area:gau]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  quo: "dash:[grid-area:quo]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  fun: "dash:[grid-area:fun]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  llm: "dash:[grid-area:llm]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  rou: "dash:[grid-area:rou]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  map: "dash:[grid-area:map]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  err: "dash:[grid-area:err]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  inp: "dash:[grid-area:inp]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
  rem: "dash:[grid-area:rem]! dash:min-h-0 dash:overflow-auto dash:p-4 dash:[&>header]:mb-2.5",
};

function KpiTile({ icon, title, value, unit, area, children }) {
  return (
    <Tile title={title} icon={icon} className={area}>
      <div className="mt-auto flex flex-wrap items-end gap-x-3 gap-y-2">
        <p className="tabular font-[family-name:var(--font-latin-first)] text-[44px] leading-none font-semibold tracking-tight text-text">
          {value}
          {unit && <span className="ml-1 text-h3 font-medium text-text-muted">{unit}</span>}
        </p>
        <div className="mb-1">{children}</div>
      </div>
    </Tile>
  );
}

function KpiRow({ health }) {
  const errPct = health.error_rate * 100;
  const p95 = health.llm_latency_ms.p95 / 1000;
  const target = health.llm_latency_ms.target / 1000;
  const requests = useCountUp(health.requests);
  return (
    <>
      <KpiTile area={AREA.k1} icon={Activity} title="คำขอทั้งหมด" value={num(Math.round(requests))}>
        <span className="text-tiny text-text-muted">ในช่วงเวลาที่เลือก</span>
      </KpiTile>
      <KpiTile area={AREA.k2} icon={ShieldAlert} title="อัตราข้อผิดพลาด" value={errPct.toFixed(1)} unit="%">
        <Pill ok={errPct <= WARN_ERROR_PCT}>{errPct <= WARN_ERROR_PCT ? `ไม่เกิน ${WARN_ERROR_PCT}%` : `เกิน ${WARN_ERROR_PCT}%`}</Pill>
      </KpiTile>
      <KpiTile area={AREA.k3} icon={Timer} title="ความหน่วง AI (p95)" value={p95.toFixed(1)} unit="วิ">
        <span className="flex flex-col items-start gap-1">
          <Pill ok={p95 <= target}>{p95 <= target ? `ไม่เกินเป้า ${target} วิ` : `เกินเป้า ${target} วิ`}</Pill>
          <span className="text-tiny text-text-muted">p50 {(health.llm_latency_ms.p50 / 1000).toFixed(1)} วิ</span>
        </span>
      </KpiTile>
    </>
  );
}

// Cache freshness map: one cell per role. Fresher data = stronger teal (one hue);
// stale, failed and empty cells add texture and an icon, so state never relies
// on colour alone. Hover or focus a cell to read it below the map.
const AGE_STEPS = [
  { max: 2, label: "0–2 วัน", tint: 100 },
  { max: 5, label: "3–5 วัน", tint: 62 },
  { max: 7, label: "6–7 วัน", tint: 32 },
];
const HATCH = "repeating-linear-gradient(45deg, var(--hatch) 0 2px, transparent 2px 6px)";

function cellStyle(r) {
  const s = cacheStatus(r);
  if (s === "error") return { background: `${HATCH}, color-mix(in oklab, var(--color-danger) 70%, transparent)`, "--hatch": "rgb(255 255 255 / 0.35)" };
  if (s === "stale") return { background: `${HATCH}, color-mix(in oklab, var(--color-warning) 70%, transparent)`, "--hatch": "rgb(255 255 255 / 0.35)" };
  if (s === "empty") return { background: HATCH, "--hatch": "var(--color-border)" };
  const step = AGE_STEPS.find((a) => (r.age_days ?? 0) <= a.max) ?? AGE_STEPS.at(-1);
  return { background: `color-mix(in oklab, var(--color-series-1) ${step.tint}%, transparent)` };
}

const STATUS_TH = { fresh: "พร้อมใช้", refreshing: "กำลังอัปเดต", stale: "เก่ากว่า 7 วัน", empty: "ยังไม่มีข้อมูล", error: "ดึงข้อมูลผิดพลาด" };

function CacheMapTile({ cache, warn, onTable }) {
  const [active, setActive] = useState(null);
  const total = cache.roles.length || 1;
  const counts = cache.roles.reduce((acc, r) => ({ ...acc, [cacheStatus(r)]: (acc[cacheStatus(r)] ?? 0) + 1 }), {});
  const over = cache.apify_runs_this_week > cache.apify_runs_budget;
  const stale = (counts.stale ?? 0) + (counts.error ?? 0);
  const shown = active ?? null;

  return (
    <Tile id="cache-map" title="ความสดข้อมูลตลาดงาน" icon={Database} warn={warn} compactWarn className={`lg:row-span-2 ${AREA.map}`}>
      <p className="-mt-3 mb-3 text-tiny text-text-muted">{cache.roles.length} สายงาน · หนึ่งช่องต่อหนึ่งสายงาน</p>
      <ul className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-tiny text-text-muted" aria-label="คำอธิบายสี">
        {AGE_STEPS.map((a) => (
          <li key={a.label} className="flex items-center gap-1.5">
            <span className="size-3 rounded-sm" style={{ background: `color-mix(in oklab, var(--color-series-1) ${a.tint}%, transparent)` }} aria-hidden="true" />
            {a.label}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span className="size-3 rounded-sm" style={cellStyle({ stale: true, fetched_at: "x" })} aria-hidden="true" />
          เก่ากว่า 7 วัน
        </li>
        <li className="flex items-center gap-1.5">
          <span className="size-3 rounded-sm border border-border" style={cellStyle({ fetched_at: null })} aria-hidden="true" />
          ยังไม่มี
        </li>
      </ul>

      <div className="grid grid-cols-6 gap-1.5" role="list" aria-label="สายงานและความสดของข้อมูล">
        {cache.roles.map((r) => {
          const s = cacheStatus(r);
          return (
            <button
              key={r.role_id}
              type="button"
              role="listitem"
              onMouseEnter={() => setActive(r)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(r)}
              onBlur={() => setActive(null)}
              aria-label={`${r.title_th}: ${STATUS_TH[s]}${r.age_days !== null ? ` อายุ ${r.age_days} วัน` : ""} · ${num(r.posting_count)} ประกาศ`}
              className={`relative flex aspect-square items-center justify-center rounded-md border dash:aspect-auto dash:h-7 transition-transform duration-150 hover:scale-110 focus-visible:scale-110 ${
                shown?.role_id === r.role_id ? "border-text" : "border-transparent"
              }`}
              style={cellStyle(r)}
            >
              {s === "refreshing" && <Loader2 className="size-3.5 animate-spin text-text motion-reduce:animate-none" strokeWidth={2.5} aria-hidden="true" />}
              {(s === "stale" || s === "error") && <AlertTriangle className="size-3.5 text-white" strokeWidth={2.5} aria-hidden="true" />}
            </button>
          );
        })}
      </div>

      <p className="mt-3 min-h-10 text-tiny text-text-muted" aria-live="polite">
        {shown ? (
          <>
            <span className="font-semibold text-text">{shown.title_th}</span> · {STATUS_TH[cacheStatus(shown)]}
            {shown.age_days !== null && ` · อายุ ${shown.age_days} วัน`} · {num(shown.posting_count)} ประกาศ
            {shown.posting_count ? ` · มีเงินเดือน ${pct(shown.salary_parsed_share)}` : ""}
          </>
        ) : (
          "ชี้หรือแตะช่องเพื่อดูรายละเอียดของสายงาน"
        )}
      </p>

      <div className="mt-2">
        <ShareStrip
          label="สถานะแคช"
          items={[
            { label: "พร้อมใช้", share: ((counts.fresh ?? 0) + (counts.refreshing ?? 0)) / total, color: "var(--color-series-1)" },
            { label: "เก่า/ผิดพลาด", share: stale / total, color: "var(--color-warning)" },
            { label: "ยังไม่มี", share: (counts.empty ?? 0) / total, color: "var(--color-border)" },
          ].filter((i) => i.share > 0)}
        />
      </div>

      <div className="mt-4">
        <Meter
          label="ดึงข้อมูล Apify สัปดาห์นี้"
          value={cache.apify_runs_this_week}
          max={cache.apify_runs_budget}
          warnAt={over ? 0 : 2}
          warnText={`เกินงบ ${cache.apify_runs_budget} ครั้งต่อสัปดาห์`}
          format={(v, max) => `${num(v)} / ${num(max)}`}
        />
      </div>

      <div className="mt-4 flex">
        <Note label="สรุปจากตัวเลข">
          {stale
            ? `${stale} สายงานต้องดู (เก่าเกิน 7 วันหรือดึงไม่สำเร็จ) ระบบใช้ข้อมูลเดิมและจะอัปเดตเองในรอบถัดไป`
            : "ข้อมูลทุกสายงานยังสดภายใน 7 วัน"}
          {` · เหลืองบดึงข้อมูล ${Math.max(0, cache.apify_runs_budget - cache.apify_runs_this_week)} ครั้งในสัปดาห์นี้`}
        </Note>
      </div>
      <button
        type="button"
        onClick={onTable}
        className="mt-3 inline-flex min-h-10 items-center justify-center gap-1.5 rounded-full border border-border px-4 text-small font-semibold text-text transition-colors duration-150 hover:bg-bg"
      >
        <Database className="size-4" strokeWidth={1.75} aria-hidden="true" />
        ดูตารางรายสายงาน
      </button>
    </Tile>
  );
}

// Sign-up funnel: one column per step, height = people at that step, with the
// share kept from the step before between columns. Hover or focus shows a bubble.
function FunnelTile({ funnel }) {
  const entered = useEntered();
  const [active, setActive] = useState(null);
  const steps = [
    { key: "registered", label: "สมัครใช้งาน", count: funnel.registered },
    { key: "input", label: "มี CV หรือแบบสอบถาม", count: funnel.with_cv_or_questionnaire },
    { key: "profile", label: "สร้างโปรไฟล์", count: funnel.profile_generated },
    { key: "role", label: "เปิดดูสายงาน", count: funnel.role_opened },
  ];
  const top = Math.max(1, steps[0].count);
  return (
    <Tile id="funnel" title="เส้นทางผู้ใช้ · จากสมัครถึงเปิดดูสายงาน" icon={Users} className={`lg:col-span-2 ${AREA.fun}`}>
      <div className="grid h-72 min-h-40 dash:h-auto dash:flex-1 grid-cols-[repeat(4,minmax(0,1fr))] items-end gap-3 border-b border-border pb-0 sm:gap-6" role="list" aria-label="จำนวนผู้ใช้ในแต่ละขั้น">
        {steps.map((s, i) => {
          const share = s.count / top;
          const kept = i > 0 && steps[i - 1].count ? s.count / steps[i - 1].count : null;
          const on = active === s.key;
          return (
            <div key={s.key} role="listitem" className="relative flex h-full flex-col justify-end">
              {kept !== null && (
                <span className="absolute top-1 -left-3 z-10 -translate-x-1/2 rounded-full border border-border bg-surface px-1.5 py-0.5 text-[11px] font-semibold text-text-muted tabular sm:-left-3" title="คงเหลือจากขั้นก่อน">
                  {pct(kept)}
                </span>
              )}
              <button
                type="button"
                onMouseEnter={() => setActive(s.key)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(s.key)}
                onBlur={() => setActive(null)}
                aria-label={`${s.label}: ${num(s.count)} คน (${pct(share)} ของผู้สมัคร)`}
                className="group relative w-full rounded-t-md transition-[height,filter] duration-700 ease-out hover:brightness-110 focus-visible:brightness-110"
                style={{
                  height: entered ? `${Math.max(4, share * 82)}%` : "0%",
                  background: `linear-gradient(180deg, color-mix(in oklab, var(--color-series-1) ${on ? 100 : 85}%, transparent), color-mix(in oklab, var(--color-series-1) 25%, transparent))`,
                  transitionDelay: `${i * 80}ms`,
                }}
              >
                <span
                  className={`absolute -top-9 left-1/2 -translate-x-1/2 rounded-full bg-text px-2.5 py-1 text-tiny font-semibold whitespace-nowrap text-bg shadow-md transition-opacity duration-150 ${
                    on ? "opacity-100" : "opacity-0"
                  }`}
                  aria-hidden="true"
                >
                  {num(s.count)} คน · {pct(share)}
                </span>
                <span className="tabular absolute inset-x-0 top-2 text-center text-small font-semibold text-text">{num(s.count)}</span>
              </button>
            </div>
          );
        })}
      </div>
      <div className="mt-2 grid grid-cols-4 gap-3 sm:gap-6">
        {steps.map((s) => (
          <p key={s.key} className="text-center text-tiny text-text-muted">
            {s.label}
          </p>
        ))}
      </div>
      <p className="mt-3 text-tiny text-text-muted">ตัวเลขบนเส้นคือสัดส่วนที่ไปต่อจากขั้นก่อน · CV ที่อ่านไม่ได้ {pct(funnel.cv_unreadable_rate)}</p>
    </Tile>
  );
}

// AI usage per model: a column of 10 segments each for tokens and requests
// against today's limit. Segments past the warning line turn amber, with an icon.
function SegmentMeter({ label, used, limit }) {
  const ratio = limit ? used / limit : 0;
  const filled = Math.round(Math.min(1, ratio) * 10);
  const warn = ratio * 100 >= WARN_LLM_PCT;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="flex h-28 w-full max-w-10 flex-col-reverse gap-0.5 dash:h-16" role="img" aria-label={`${label} ${pct(ratio)} ของขีดจำกัด`}>
        {Array.from({ length: 10 }, (_, i) => (
          <span
            key={i}
            className={`flex-1 rounded-[3px] ${i < filled ? (warn && i >= WARN_LLM_PCT / 10 - 1 ? "bg-warning" : "bg-[var(--color-series-1)]") : "bg-border/70"}`}
          />
        ))}
      </div>
      <span className="flex items-center gap-1 text-tiny text-text-muted">
        {warn && <AlertTriangle className="size-3 text-warning" strokeWidth={2.5} aria-hidden="true" />}
        <span className={`tabular font-semibold ${warn ? "text-warning" : "text-text"}`}>{pct(ratio)}</span>
      </span>
    </div>
  );
}

function LlmTile({ llm, warn }) {
  const worst = llm.models.reduce(
    (w, m) => {
      const r = Math.max(m.tokens_used / m.tokens_limit, m.requests_used / m.requests_limit);
      return r > w.r ? { r, m } : w;
    },
    { r: 0, m: null },
  );
  return (
    <Tile id="llm" title="การใช้ AI วันนี้" icon={Cpu} warn={warn} className={AREA.llm}>
      <div className="grid grid-cols-3 gap-4">
        {llm.models.map((m) => (
          <div key={`${m.model}-${m.role}`} className="flex min-w-0 flex-col items-center">
            <p className="mb-2 truncate text-tiny font-semibold text-text" title={m.model}>
              {ROLE_TH[m.role] ?? m.role}
            </p>
            <div className="grid w-full grid-cols-2 gap-2.5">
              <SegmentMeter label="โทเคน" used={m.tokens_used} limit={m.tokens_limit} />
              <SegmentMeter label="คำขอ" used={m.requests_used} limit={m.requests_limit} />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-tiny text-text-muted">แต่ละโมเดล: แท่งซ้าย = โทเคน · แท่งขวา = คำขอ เทียบขีดจำกัดวันนี้</p>
      <p className="mt-1 text-tiny text-text-muted">
        429 rate limit {num(llm.rate_limited_429)} ครั้ง · เรียกโมเดลสำรอง {num(llm.fallback_calls)} ครั้ง
      </p>
      {llm.jev?.calls > 0 && (
        <p className="mt-1 text-tiny text-text-muted">
          Jev เลือกเส้นทาง {num(llm.jev.calls)} ครั้ง · ล้มเหลว {num(llm.jev.failed)} ครั้ง · {num(llm.jev.input_tokens)} โทเคน
        </p>
      )}
      {/* In the fit layout the tile's badge and the header's warning list carry this. */}
      <div className="mt-3 flex flex-1 dash:hidden">
        <Note icon={worst.r * 100 >= WARN_LLM_PCT ? AlertTriangle : Info} label={worst.r * 100 >= WARN_LLM_PCT ? "ใกล้ขีดจำกัด" : "สรุปจากตัวเลข"}>
          {worst.m
            ? `${ROLE_TH[worst.m.role] ?? worst.m.role} ใช้ไปมากที่สุด ${pct(worst.r)} ของขีดจำกัดวันนี้${worst.r * 100 >= WARN_LLM_PCT ? ` (เกิน ${WARN_LLM_PCT}%)` : ""}`
            : "ยังไม่มีการใช้ AI วันนี้"}
        </Note>
      </div>
    </Tile>
  );
}

// Highlight card: the funnel's overall conversion and its biggest drop, worked
// out from the numbers on this page.
function InsightCard({ funnel }) {
  const steps = [
    ["สมัครใช้งาน", funnel.registered],
    ["มี CV หรือแบบสอบถาม", funnel.with_cv_or_questionnaire],
    ["สร้างโปรไฟล์", funnel.profile_generated],
    ["เปิดดูสายงาน", funnel.role_opened],
  ];
  const overall = funnel.registered ? funnel.role_opened / funnel.registered : 0;
  let drop = { lost: -1 };
  for (let i = 1; i < steps.length; i += 1) {
    const lost = steps[i - 1][1] ? 1 - steps[i][1] / steps[i - 1][1] : 0;
    if (lost > drop.lost) drop = { lost, from: steps[i - 1][0], to: steps[i][0] };
  }
  const blocks = Math.round(overall * 10);
  return (
    <section aria-label="ข้อสังเกต" className={`bg-curtain relative isolate flex flex-col overflow-hidden rounded-2xl p-5 text-curtain-fg shadow-sm ${AREA.ins}`}>
      <DotGrid intensity={0.45} clear={0.5} className="-z-10" />
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-tiny font-semibold">
        <Lightbulb className="size-3.5" strokeWidth={2} aria-hidden="true" />
        ข้อสังเกต
      </span>
      <p className="mt-4 text-h3 leading-8 font-semibold dash:mt-3 dash:text-body dash:leading-7">
        ผู้สมัคร{" "}
        <span className="rounded-full bg-curtain-accent px-2 text-[#0c1922] tabular">{pct(overall)}</span> ไปถึงการเปิดดูสายงาน
        {drop.from && (
          <>
            {" "}
            · หลุดมากที่สุดช่วง “{drop.from} → {drop.to}” ({pct(drop.lost)})
          </>
        )}
      </p>
      <div className="mt-auto flex gap-1 pt-5" role="img" aria-label={`ไปถึงขั้นสุดท้าย ${pct(overall)}`}>
        {Array.from({ length: 10 }, (_, i) => (
          <span key={i} className={`h-4 flex-1 rounded ${i < blocks ? "bg-curtain-accent" : "bg-white/10"}`} />
        ))}
      </div>
      <p className="mt-2 text-tiny text-curtain-muted">คำนวณจากตัวเลขในหน้านี้ ไม่ใช่การคาดการณ์ของ AI</p>
    </section>
  );
}

const SERIES = ["var(--color-series-1)", "var(--color-series-2)", "var(--color-series-3)"];

function RouterTile({ router, warn }) {
  const sorted = [...router.by_route].sort((a, b) => b.share - a.share);
  const shown = sorted.slice(0, 6);
  const rest = sorted.slice(6).reduce((s, r) => s + r.share, 0);
  const rows = rest > 0 ? [...shown, { route: `อื่น ๆ (${sorted.length - 6})`, share: rest, other: true }] : shown;
  const top = rows[0]?.share || 1;
  return (
    <Tile id="router" title={`AI Router · ${num(router.messages)} ข้อความ`} icon={Route} warn={warn} className={`lg:col-span-2 ${AREA.rou}`}>
      <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
        <div>
          <h3 className="mb-2 text-tiny font-semibold text-text-muted">สัดส่วนเส้นทาง</h3>
          <ul className="space-y-1.5">
            {rows.map((r) => (
              <li key={r.route} className="grid grid-cols-[minmax(0,auto)_1fr_auto] items-center gap-2 text-small">
                <code className={`truncate ${r.other ? "text-text-muted" : "text-text"}`}>{r.route}</code>
                <span className="relative h-1.5 rounded-full border-b border-dashed border-border" aria-hidden="true">
                  <span className="absolute inset-y-0 left-0 rounded-full bg-[var(--color-series-1)]" style={{ width: `${(r.share / top) * 100}%`, opacity: r.other ? 0.4 : 0.9 }} />
                </span>
                <span className="tabular text-right font-semibold text-text">{pct(r.share)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col gap-4">
          <div>
            <h3 className="mb-2 text-tiny font-semibold text-text-muted">ตัดสินใจโดย</h3>
            <ShareStrip
              label="ตัดสินใจโดย"
              items={[
                { label: "กฎ", share: router.by_layer.rules, color: SERIES[0] },
                { label: "LLM", share: router.by_layer.llm, color: SERIES[1] },
                { label: "ตัวกรอง", share: router.by_layer.guard, color: SERIES[2] },
              ]}
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <MiniStat label="clarify" value={pct(router.clarify_rate)} />
            <MiniStat label="decline" value={pct(router.decline_rate)} />
            <MiniStat label="มั่นใจต่ำ" value={pct(router.low_confidence_rate)} />
          </div>
        </div>
      </div>
    </Tile>
  );
}

// Average completeness when profiles are generated, as a segmented arc with the
// generate threshold marked.
function GaugeTile({ value }) {
  const entered = useEntered();
  const shown = useCountUp(value);
  const SEGS = 22;
  const lit = entered ? Math.round((Math.min(100, value) / 100) * SEGS) : 0;
  const cx = 110;
  const cy = 112;
  const segs = Array.from({ length: SEGS }, (_, i) => {
    const a = Math.PI + (i / (SEGS - 1)) * Math.PI; // left to right over the top
    const r1 = 72;
    const r2 = 98;
    return { i, x1: cx + r1 * Math.cos(a), y1: cy + r1 * Math.sin(a), x2: cx + r2 * Math.cos(a), y2: cy + r2 * Math.sin(a) };
  });
  const tA = Math.PI + (THRESHOLD / 100) * Math.PI;
  return (
    <Tile id="gauge" title="ความครบถ้วนเฉลี่ยตอนสร้างโปรไฟล์" icon={Gauge} className={AREA.gau}>
      <div className="relative mx-auto mt-auto w-full max-w-[240px]">
        <svg viewBox="0 0 220 128" className="w-full" role="img" aria-label={`เฉลี่ย ${Math.round(value)}% เกณฑ์สร้างโปรไฟล์ ${THRESHOLD}%`}>
          {segs.map((s) => (
            <line
              key={s.i}
              x1={s.x1}
              y1={s.y1}
              x2={s.x2}
              y2={s.y2}
              stroke={s.i < lit ? "var(--color-series-1)" : "var(--color-border)"}
              strokeWidth="9"
              strokeLinecap="round"
              style={{ transition: "stroke 300ms ease-out", transitionDelay: `${s.i * 25}ms` }}
            />
          ))}
          <line x1={cx + 62 * Math.cos(tA)} y1={cy + 62 * Math.sin(tA)} x2={cx + 106 * Math.cos(tA)} y2={cy + 106 * Math.sin(tA)} stroke="var(--color-text)" strokeWidth="2" strokeDasharray="3 3" />
        </svg>
        <p className="tabular absolute inset-x-0 bottom-1 text-center font-[family-name:var(--font-latin-first)] text-[36px] leading-none font-semibold text-text">
          {Math.round(shown)}%
        </p>
      </div>
      <p className="mt-2 text-center text-tiny text-text-muted">เส้นประคือเกณฑ์สร้างโปรไฟล์ {THRESHOLD}%</p>
    </Tile>
  );
}

function QuotaTile({ quota }) {
  const base = Math.max(1, quota.users_active);
  const rows = [
    { label: "ใช้งานวันนี้", count: quota.users_active, tone: "var(--color-series-1)" },
    { label: "ใช้เกิน 80%", count: quota.users_over_80pct, tone: "color-mix(in oklab, var(--color-series-1) 55%, transparent)" },
    { label: "ใช้ครบโควตา", count: quota.users_exhausted, tone: "var(--color-warning)", warn: quota.users_exhausted > 0 },
  ];
  return (
    <Tile id="quota" title="โควตาผู้ใช้วันนี้" icon={Gauge} className={AREA.quo}>
      <ul className="space-y-3 dash:space-y-2">
        {rows.map((r) => (
          <li key={r.label}>
            <div className="mb-1 flex items-baseline justify-between text-small">
              <span className="flex items-center gap-1.5 text-text">
                {r.warn && <AlertTriangle className="size-3.5 text-warning" strokeWidth={2} aria-hidden="true" />}
                {r.label}
              </span>
              <span className="tabular font-semibold text-text">{num(r.count)} คน</span>
            </div>
            <span className="block h-2 overflow-hidden rounded-full bg-border" aria-hidden="true">
              <span className="block h-full rounded-full" style={{ width: `${(r.count / base) * 100}%`, background: r.tone }} />
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-tiny text-text-muted">
        ใช้ไปวันนี้ <span className="tabular font-semibold text-text">{num(quota.requests_used)}</span> คำขอ ·{" "}
        <span className="tabular font-semibold text-text">{num(quota.tokens_used)}</span> โทเคน
      </p>
    </Tile>
  );
}

function ErrorsTile({ health, warn }) {
  const errors = [...health.errors_by_code].sort((a, b) => {
    const pa = PRIORITY_CODES.indexOf(a.code);
    const pb = PRIORITY_CODES.indexOf(b.code);
    return (pa === -1 ? 99 : pa) - (pb === -1 ? 99 : pb) || b.count - a.count;
  });
  return (
    <Tile id="errors" title="ข้อผิดพลาดแยกตามรหัส" icon={XCircle} warn={warn} className={`lg:col-span-2 ${AREA.err}`}>
      {errors.length ? (
        <CountBars items={errors.map((e) => ({ key: e.code, label: e.code, count: e.count, mono: true, warn: PRIORITY_CODES.includes(e.code) }))} />
      ) : (
        <p className="text-small text-text-muted">ไม่มีข้อผิดพลาด</p>
      )}
      <p className="mt-3 text-tiny text-text-muted">
        <AlertTriangle className="mr-1 inline size-3.5 text-warning" strokeWidth={2} aria-hidden="true" />
        รหัสที่ต้องดูก่อน (AI ล่ม หมดเวลา ระบบผิดพลาด rate limit) แสดงไว้บนสุด
      </p>
    </Tile>
  );
}

function InputsTile({ funnel }) {
  const e = funnel.edits;
  const editsTotal = e.applied + e.rejected + e.expired;
  return (
    <Tile id="inputs" title="ข้อมูลที่ผู้ใช้ให้และการแก้ผ่านแชท" icon={ClipboardList} className={AREA.inp}>
      <h3 className="mb-2 text-tiny font-semibold text-text-muted">ข้อมูลที่ใช้สร้างโปรไฟล์</h3>
      <ShareStrip
        label="ข้อมูลที่ผู้ใช้ให้"
        items={[
          { label: "CV", share: funnel.input_mix.cv_only, color: SERIES[0] },
          { label: "แบบสอบถาม", share: funnel.input_mix.questionnaire_only, color: SERIES[1] },
          { label: "ทั้งสองอย่าง", share: funnel.input_mix.both, color: SERIES[2] },
        ]}
      />
      <h3 className="mt-5 mb-2 text-tiny font-semibold text-text-muted">ข้อเสนอแก้โปรไฟล์ ({num(editsTotal)})</h3>
      <ShareStrip
        label="การแก้ผ่านแชท"
        items={[
          { label: "ยืนยัน", share: editsTotal ? e.applied / editsTotal : 0, color: SERIES[0] },
          { label: "ยกเลิก", share: editsTotal ? e.rejected / editsTotal : 0, color: SERIES[1] },
          { label: "หมดเวลา", share: editsTotal ? e.expired / editsTotal : 0, color: SERIES[2] },
        ]}
      />
    </Tile>
  );
}

function RemovedSkillsTile({ funnel }) {
  return (
    <Tile id="removed" title="ทักษะที่ถูกลบบ่อยที่สุด" icon={Trash2} className={`lg:col-span-2 ${AREA.rem}`}>
      {funnel.top_removed_skills.length ? (
        <CountBars items={funnel.top_removed_skills.map((s) => ({ key: s.skill_id, label: s.name_th, count: s.count }))} />
      ) : (
        <p className="text-small text-text-muted">ยังไม่มีการลบทักษะ</p>
      )}
      <p className="mt-3 text-tiny text-text-muted">ทักษะที่ผู้ใช้ลบบ่อยอาจถูกดึงจาก CV ผิด ลองตรวจกฎการอ่าน CV</p>
    </Tile>
  );
}

const CACHE_COLUMNS = [
  { key: "title_th", label: "สายงาน" },
  { key: "age_days", label: "อายุข้อมูล", numeric: true },
  { key: "status", label: "สถานะ" },
  { key: "posting_count", label: "ประกาศงาน", numeric: true },
  { key: "salary_parsed_share", label: "มีเงินเดือน %", numeric: true },
  { key: "has_reference_salary", label: "เงินเดือนอ้างอิง" },
  { key: "last_error", label: "ข้อผิดพลาดล่าสุด" },
];
const STATUS_ORDER = { error: 0, stale: 1, refreshing: 2, empty: 3, fresh: 4 };
const cacheStatus = (r) => (r.last_error ? "error" : r.refreshing ? "refreshing" : r.fetched_at === null ? "empty" : r.stale ? "stale" : "fresh");

function CacheStatus({ row }) {
  const s = cacheStatus(row);
  if (s === "refreshing") {
    return (
      <span className="inline-flex items-center gap-1.5 text-text-muted">
        <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" strokeWidth={2} aria-hidden="true" />
        กำลังอัปเดต
      </span>
    );
  }
  if (s === "error" || s === "stale") {
    return (
      <span className="inline-flex items-center gap-1.5 font-medium text-warning">
        <AlertTriangle className="size-3.5" strokeWidth={2} aria-hidden="true" />
        {s === "error" ? "ดึงข้อมูลผิดพลาด" : "เก่ากว่า 7 วัน"}
      </span>
    );
  }
  if (s === "empty") return <span className="text-text-muted">ยังไม่มีข้อมูล</span>;
  return (
    <span className="inline-flex items-center gap-1.5 text-success">
      <CheckCircle2 className="size-3.5" strokeWidth={2} aria-hidden="true" />
      พร้อมใช้
    </span>
  );
}

/** The full cache table (the map's table view), sortable, in a dialog opened from the map. */
function CacheTableDialog({ cache, open, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  const [sort, setSort] = useState({ key: "status", dir: "asc" });
  const rows = useMemo(() => {
    const value = (r) => (sort.key === "status" ? STATUS_ORDER[cacheStatus(r)] : sort.key === "age_days" ? (r.age_days ?? 999) : r[sort.key]);
    return [...cache.roles].sort((a, b) => {
      const va = value(a);
      const vb = value(b);
      const c = typeof va === "string" ? va.localeCompare(vb, "th") : Number(va ?? -1) - Number(vb ?? -1);
      return sort.dir === "asc" ? c : -c;
    });
  }, [cache.roles, sort]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="cache-table-title"
      className="m-auto w-[min(1100px,calc(100vw-2rem))] rounded-2xl border border-border bg-bg p-0 text-text shadow-xl backdrop:bg-black/60"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h2 id="cache-table-title" className="flex items-center gap-2 text-small font-semibold">
            <Database className="size-4 text-text-muted" strokeWidth={1.75} aria-hidden="true" />
            ตารางข้อมูลตลาดงานรายสายงาน · {cache.roles.length} สายงาน
          </h2>
          <p className="mt-0.5 text-tiny text-text-muted">ข้อมูลกรุงเทพฯ · ระบบอัปเดตเองทุก 7 วัน หน้านี้ไม่สั่งดึงข้อมูล · กดหัวคอลัมน์เพื่อเรียง</p>
        </div>
        <button type="button" onClick={onClose} aria-label="ปิดตาราง" className="inline-flex size-9 items-center justify-center rounded-md text-text-muted hover:bg-bg hover:text-text">
          <XCircle className="size-5" strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>
      <div className="max-h-[70vh] overflow-auto px-5 pb-4">
        <table className="w-full min-w-[720px] text-left text-small">
          <thead className="sticky top-0 bg-bg">
            <tr className="border-b border-border text-tiny text-text-muted">
              {CACHE_COLUMNS.map((c) => {
                const active = sort.key === c.key;
                return (
                  <th key={c.key} scope="col" aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"} className={`py-2 pr-3 font-semibold ${c.numeric ? "text-right" : ""}`}>
                    <button
                      type="button"
                      onClick={() => setSort({ key: c.key, dir: active && sort.dir === "asc" ? "desc" : "asc" })}
                      className={`inline-flex min-h-9 items-center gap-1 rounded-sm hover:text-text ${active ? "text-text" : ""}`}
                    >
                      {c.label}
                      {active && (sort.dir === "asc" ? <ArrowUp className="size-3" strokeWidth={2} aria-hidden="true" /> : <ArrowDown className="size-3" strokeWidth={2} aria-hidden="true" />)}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.role_id} className="border-b border-border last:border-0">
                <th scope="row" className="py-2.5 pr-3 font-medium text-text">
                  <Link href={`/roles/${r.role_id}`} className="hover:underline">
                    {r.title_th}
                  </Link>
                </th>
                <td className={`tabular py-2.5 pr-3 text-right ${r.stale ? "font-semibold text-warning" : "text-text"}`} title={r.fetched_at ? dateTh(r.fetched_at) : undefined}>
                  {r.age_days === null ? "–" : `${r.age_days} วัน`}
                </td>
                <td className="py-2.5 pr-3">
                  <CacheStatus row={r} />
                </td>
                <td className="tabular py-2.5 pr-3 text-right text-text">{num(r.posting_count)}</td>
                <td className="tabular py-2.5 pr-3 text-right text-text">{r.posting_count ? pct(r.salary_parsed_share) : "–"}</td>
                <td className="py-2.5 pr-3 text-text">{r.has_reference_salary ? "มี" : <span className="text-text-muted">ไม่มี</span>}</td>
                <td className="py-2.5 font-[family-name:var(--font-latin-first)] text-tiny text-warning">{r.last_error ?? <span className="text-text-muted">–</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </dialog>
  );
}

/** API / database / last request, as chips beside the title. */
function HealthChips({ health }) {
  const chip = (ok, Icon, label) => (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-tiny text-text">
      <Icon className="size-3.5 text-text-muted" strokeWidth={1.75} aria-hidden="true" />
      {label}
      {ok ? <CheckCircle2 className="size-3.5 text-success" strokeWidth={2} aria-label="ปกติ" /> : <XCircle className="size-3.5 text-danger" strokeWidth={2} aria-label="มีปัญหา" />}
    </span>
  );
  return (
    <div className="flex flex-wrap items-center gap-2">
      {chip(health.api === "ok", Server, health.api === "ok" ? "API พร้อมใช้" : "API มีปัญหา")}
      {chip(health.db === "ok", Database, health.db === "ok" ? "ฐานข้อมูลพร้อมใช้" : "ฐานข้อมูลติดต่อไม่ได้")}
      <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-tiny text-text-muted">
        <Clock className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
        คำขอล่าสุด {health.last_request_at ? `${timeTh(health.last_request_at)} น.` : "–"}
      </span>
    </div>
  );
}

/* ---------- fit to screen ---------- */

// Same media query as the `dash` variant in globals.css.
const FIT_QUERY = "(min-width: 1280px) and (min-height: 800px)";
const TOP_BAR = 65; // top bar height + its 1 px border
const DESIGN_HEIGHT = 1015; // the height the fit layout is designed for (a 1080 px screen)
const MIN_ZOOM = 0.8; // below this text gets too small; tiles scroll inside instead

const subscribeResize = (cb) => {
  window.addEventListener("resize", cb);
  return () => window.removeEventListener("resize", cb);
};

/** Zoom that fits the whole dashboard in the window height (null outside the fit layout). */
function useFitZoom() {
  const value = useSyncExternalStore(
    subscribeResize,
    () => {
      if (!window.matchMedia(FIT_QUERY).matches) return "";
      const z = Math.min(1, Math.max(MIN_ZOOM, (window.innerHeight - TOP_BAR) / DESIGN_HEIGHT));
      return z.toFixed(3);
    },
    () => "",
  );
  return value ? Number(value) : null;
}

/* ---------- page ---------- */

function Forbidden() {
  return (
    <div className="mx-auto mt-10 flex max-w-md flex-col items-center rounded-xl border border-border bg-surface px-6 py-14 text-center">
      <ShieldAlert className="size-10 text-text-muted" strokeWidth={1.5} aria-hidden="true" />
      <h1 className="mt-4 text-h3 font-semibold text-text">หน้านี้สำหรับผู้ดูแลระบบเท่านั้น</h1>
      <Link href="/start" className="mt-5 inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-small font-semibold text-on-primary hover:bg-primary-hover">
        กลับไปหน้าหลัก
      </Link>
    </div>
  );
}

export function AdminDashboard() {
  const session = useSession();
  const [win, setWin] = useState("today");
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cacheTable, setCacheTable] = useState(false);
  const requestRef = useRef(0);

  const load = useCallback((w) => {
    requestRef.current += 1;
    const id = requestRef.current;
    setLoading(true);
    return data.adminOverview(w).then(
      (o) => {
        if (id !== requestRef.current) return; // a newer window was picked
        setError(null);
        setOverview(o);
        setLoading(false);
      },
      (e) => {
        if (id !== requestRef.current) return;
        setError(e);
        setLoading(false);
      },
    );
  }, []);

  const isAdmin = session.status === "ready" && session.user?.is_admin;
  const zoom = useFitZoom();
  usePageReady(session.status === "error" || (session.status === "ready" && (!isAdmin || Boolean(overview || error))));

  // Load on open and on window change, then every 60 s while the tab is visible (FR-45).
  useEffect(() => {
    if (!isAdmin) return;
    // First load on the next tick, so the loading state is not set inside the effect body.
    const first = setTimeout(() => load(win), 0);
    const t = setInterval(() => {
      if (document.visibilityState === "visible") load(win);
    }, REFRESH_MS);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [isAdmin, win, load]);

  // Full width: the dashboard uses the whole screen (no 1120 px cap like other pages).
  // In the fit layout the page is scaled to the window height (zoom), and its height is
  // set in unzoomed pixels so that, once scaled, it fills the space under the top bar.
  const wrap = (children) => (
    <div
      className="w-full px-4 pt-6 pb-24 md:px-6 dash:flex dash:flex-col dash:px-8 dash:pt-4 dash:pb-4"
      style={zoom ? { zoom, height: `calc((100dvh - ${TOP_BAR}px) / ${zoom})` } : undefined}
    >
      {children}
    </div>
  );

  if (session.status === "error") return wrap(<ErrorState error={session.error} onRetry={() => window.location.reload()} />);
  if (session.status !== "ready") return wrap(<LoadingBlock lines={8} label="กำลังโหลด…" />);
  if (!isAdmin || error?.code === "FORBIDDEN") return wrap(<Forbidden />);

  const warnPanels = new Set((overview?.warnings ?? []).map((w) => w.panel));

  return wrap(
    <>
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 dash:flex-nowrap">
        <div className="min-w-0 dash:flex-1">
          <h1 className="text-h2 font-bold text-text">ภาพรวมการทำงานของระบบ</h1>
          <p className="mt-0.5 text-tiny text-text-muted dash:truncate">
            อ่านอย่างเดียว · ตัวเลขรวมเท่านั้น ไม่แสดงข้อมูลส่วนบุคคล · อัปเดตเองทุก 60 วินาที
            {overview && ` · อัปเดตล่าสุด ${dateTh(overview.generated_at)} ${timeTh(overview.generated_at)} น.`}
            {" · "}ช่วงเวลาใช้กับคำขอ ข้อผิดพลาด Router และเส้นทางผู้ใช้ · การใช้ AI และโควตาเป็นของวันนี้
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 dash:shrink-0 dash:flex-nowrap">
          {overview && <HealthChips health={overview.health} />}
          {overview && <Warnings warnings={overview.warnings} />}
          <WindowSwitch value={win} onChange={setWin} />
          <Button variant="secondary" onClick={() => load(win)} loading={loading}>
            {!loading && <RefreshCw className="size-4" strokeWidth={2} aria-hidden="true" />}
            รีเฟรช
          </Button>
        </div>
      </header>

      {error && (
        <div className="mt-4">
          <ErrorState error={error} onRetry={() => load(win)} />
        </div>
      )}

      {!overview ? (
        !error && (
          <div className="mt-4">
            <LoadingBlock lines={8} label="กำลังโหลดข้อมูลแดชบอร์ด…" />
          </div>
        )
      ) : (
        <>
          <div
            className={`mt-4 grid gap-4 transition-opacity duration-150 md:grid-cols-2 lg:grid-cols-4 dash:min-h-0 dash:flex-1 dash:grid-cols-6 dash:grid-rows-[minmax(0,0.78fr)_minmax(0,1fr)_minmax(0,1fr)] dash:gap-3 dash:[grid-template-areas:'k1_k2_k3_ins_gau_quo'_'fun_fun_llm_rou_rou_map'_'err_err_inp_rem_rem_map'] ${
              loading ? "opacity-70" : ""
            }`}
            aria-busy={loading}
          >
            <KpiRow health={overview.health} />
            <InsightCard funnel={overview.funnel} />
            <GaugeTile value={overview.funnel.avg_completeness_at_generate} />
            <QuotaTile quota={overview.quota} />
            <FunnelTile funnel={overview.funnel} />
            <LlmTile llm={overview.llm} warn={warnPanels.has("llm")} />
            <RouterTile router={overview.router} warn={warnPanels.has("router")} />
            <CacheMapTile cache={overview.cache} warn={warnPanels.has("cache")} onTable={() => setCacheTable(true)} />
            <ErrorsTile health={overview.health} warn={warnPanels.has("health")} />
            <InputsTile funnel={overview.funnel} />
            <RemovedSkillsTile funnel={overview.funnel} />
          </div>
          <CacheTableDialog cache={overview.cache} open={cacheTable} onClose={() => setCacheTable(false)} />
        </>
      )}
    </>,
  );
}
