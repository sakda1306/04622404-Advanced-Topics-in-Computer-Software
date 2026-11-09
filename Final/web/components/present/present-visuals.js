"use client";

import { useEntered } from "@/lib/use-motion";
import { Explain } from "@/components/present/explain";

// Small animated pieces for the presentation page (/present). Bars grow once when
// the page has loaded; with reduced motion the final width shows at once.

/**
 * One horizontal bar: label, bar (share of `max`), value text. `strong` marks the bar to look at.
 * `tip` adds a hover explanation (see explain.js).
 */
export function GrowBar({ label, value, max = 1, text, strong = false, mark, delay = 0, tip }) {
  const entered = useEntered();
  const share = Math.max(0, Math.min(1, value / max));
  return (
    <Explain as="li" tip={tip} title={tip ? label : undefined} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 rounded-md text-small">
      <span className={`truncate ${strong ? "font-semibold text-text" : "text-text-muted"}`}>{label}</span>
      <span className="relative h-3 rounded-full bg-border" aria-hidden="true">
        <span
          className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-[900ms] ease-out"
          style={{
            width: entered ? `${share * 100}%` : "0%",
            background: strong ? "var(--color-series-1)" : "color-mix(in oklab, var(--color-series-1) 45%, transparent)",
            transitionDelay: `${delay}ms`,
          }}
        />
        {mark !== undefined && (
          <span className="absolute -top-1.5 -bottom-1.5 w-0 border-l-2 border-dashed border-text" style={{ left: `${(mark / max) * 100}%` }} />
        )}
      </span>
      <span className={`tabular w-14 text-right ${strong ? "font-semibold text-text" : "text-text-muted"}`}>{text}</span>
    </Explain>
  );
}

/** Vertical column chart for a handful of values (0..max), each with a label under it. */
export function Columns({ items, max = 1, height = "h-44", threshold, thresholdLabel }) {
  const entered = useEntered();
  return (
    <div>
      <div className={`relative grid ${height} grid-cols-[repeat(var(--n),minmax(0,1fr))] items-end gap-4 border-b border-border`} style={{ "--n": items.length }}>
        {threshold !== undefined && (
          <span className="pointer-events-none absolute inset-x-0 border-t-2 border-dashed border-text/60" style={{ bottom: `${(threshold / max) * 100}%` }}>
            <span className="absolute -top-5 right-0 text-[11px] font-semibold text-text-muted">{thresholdLabel}</span>
          </span>
        )}
        {items.map((it, i) => (
          <div key={it.label} className="flex h-full flex-col items-center justify-end">
            <span className="tabular mb-1 text-small font-semibold text-text">{it.text}</span>
            <span
              className="w-full max-w-16 rounded-t-md transition-[height] duration-[900ms] ease-out"
              style={{
                height: entered ? `${(it.value / max) * 100}%` : "0%",
                background: it.strong ? "var(--color-series-1)" : "color-mix(in oklab, var(--color-series-1) 45%, transparent)",
                transitionDelay: `${i * 90}ms`,
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 grid grid-cols-[repeat(var(--n),minmax(0,1fr))] gap-4" style={{ "--n": items.length }}>
        {items.map((it) => (
          <p key={it.label} className="text-center text-tiny leading-4 text-text-muted">
            {it.label}
          </p>
        ))}
      </div>
    </div>
  );
}

/** Used vs limit, with the figure in text. */
export function UsageMeter({ label, used, limit, unit }) {
  const entered = useEntered();
  const share = Math.min(1, used / limit);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-small">
        <span className="text-text">{label}</span>
        <span className="tabular text-text-muted">
          <span className="font-semibold text-text">{used.toLocaleString("th-TH")}</span> / {limit.toLocaleString("th-TH")} {unit}
        </span>
      </div>
      <span className="block h-2.5 overflow-hidden rounded-full bg-border" aria-hidden="true">
        <span className="block h-full rounded-full bg-[var(--color-series-1)] transition-[width] duration-[900ms] ease-out" style={{ width: entered ? `${share * 100}%` : "0%" }} />
      </span>
    </div>
  );
}
