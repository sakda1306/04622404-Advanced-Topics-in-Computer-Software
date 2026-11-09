"use client";

import { AlertTriangle, CheckCircle2, Info } from "lucide-react";

// Bento dashboard pieces shared by the admin dashboard and the profile page:
// frosted tiles, status pills (icon + text), computed notes, small stats and the
// parts-of-a-whole strip. Series colours come from --color-series-1..3
// (validated in both themes, globals.css).

export const pct = (r) => `${Math.round(r * 100)}%`;

/** One bento tile: rounded, frosted surface, a title row with an optional icon and action. */
export function Tile({ id, title, icon: Icon, action, warn = false, compactWarn = false, className = "", children }) {
  return (
    <section
      aria-labelledby={id ? `tile-${id}` : undefined}
      className={`flex min-w-0 flex-col rounded-2xl border bg-glass p-5 shadow-sm ${warn ? "border-warning/60" : "border-border"} ${className}`}
    >
      {title && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <h2 id={id ? `tile-${id}` : undefined} className="flex items-center gap-2 text-small font-semibold text-text">
            {Icon && <Icon className="size-4 text-text-muted" strokeWidth={1.75} aria-hidden="true" />}
            {title}
          </h2>
          {action}
          {warn && !action && <WarnBadge compact={compactWarn} />}
        </header>
      )}
      {children}
    </section>
  );
}

export function WarnBadge({ compact = false }) {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-warning px-2 py-0.5 text-tiny font-medium text-warning"
      title={compact ? "มีคำเตือน" : undefined}
    >
      <AlertTriangle className="size-3.5" strokeWidth={2} aria-hidden="true" />
      {compact ? <span className="sr-only">มีคำเตือน</span> : "มีคำเตือน"}
    </span>
  );
}

/** Status pill: icon + text, never colour alone. */
export function Pill({ ok, children }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-tiny font-semibold ${
        ok ? "bg-success/15 text-success" : "bg-warning/15 text-warning"
      }`}
    >
      {ok ? (
        <CheckCircle2 className="size-3.5" strokeWidth={2.25} aria-hidden="true" />
      ) : (
        <AlertTriangle className="size-3.5" strokeWidth={2.25} aria-hidden="true" />
      )}
      {children}
    </span>
  );
}

/** A computed note under a chart (from the numbers on this page, not from AI). */
export function Note({ icon: Icon = Info, label, children }) {
  return (
    <p className="mt-auto flex items-start gap-2.5 rounded-xl border border-border bg-bg/60 px-3.5 py-3 backdrop-blur-md text-tiny text-text">
      <Icon className="mt-0.5 size-4 shrink-0 text-text-muted" strokeWidth={1.75} aria-hidden="true" />
      <span>
        <span className="font-semibold">{label}: </span>
        {children}
      </span>
    </p>
  );
}

export function MiniStat({ label, value, warn = false }) {
  return (
    <div className="rounded-xl border border-border bg-bg/60 px-3 py-2.5 backdrop-blur-md">
      <p className="text-tiny text-text-muted">{label}</p>
      <p className={`tabular mt-0.5 text-h3 font-semibold ${warn ? "text-warning" : "text-text"}`}>{value}</p>
    </div>
  );
}

/** Parts of a whole as one stacked strip (2 px gaps) with a direct-labelled legend. */
export function ShareStrip({ items, label }) {
  return (
    <div>
      <div
        className="flex h-3 gap-0.5 overflow-hidden rounded-full"
        role="img"
        aria-label={`${label}: ${items.map((i) => `${i.label} ${pct(i.share)}`).join(", ")}`}
      >
        {items.map((i) => (
          <span
            key={i.label}
            className="h-full first:rounded-l-full last:rounded-r-full"
            style={{ width: `${i.share * 100}%`, background: i.color }}
            title={`${i.label} ${pct(i.share)}`}
          />
        ))}
      </div>
      <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
        {items.map((i) => (
          <li key={i.label} className="flex items-center gap-1.5 text-tiny text-text-muted">
            <span className="size-2.5 rounded-sm" style={{ background: i.color }} aria-hidden="true" />
            {i.label} <span className="tabular font-semibold text-text">{pct(i.share)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
