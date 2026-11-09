"use client";

import { AlertTriangle } from "lucide-react";
import { useCountUp, useEntered } from "@/lib/use-motion";

/**
 * Meter: one value against a limit (match %, completeness, usage).
 * The bar grows in once; the number counts up with it. Warning state adds an
 * icon and text, never colour alone.
 */
export function Meter({ label, value, max = 100, format = (v) => `${Math.round(v)}%`, warnAt, warnText, size = "md" }) {
  const entered = useEntered();
  const ratio = Math.max(0, Math.min(1, value / max));
  const shown = useCountUp(value);
  const warn = warnAt !== undefined && ratio >= warnAt;

  return (
    <div>
      {label && (
        <div className="mb-1.5 flex items-baseline justify-between gap-3">
          <span className="text-small text-text">{label}</span>
          <span className="tabular text-small font-medium text-text">{format(shown, max)}</span>
        </div>
      )}
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={Math.round(value)}
        className={`overflow-hidden rounded-full bg-border ${size === "lg" ? "h-3" : "h-2"}`}
      >
        <div
          className="h-full rounded-full transition-[width] duration-[800ms] ease-out"
          style={{
            width: entered ? `${ratio * 100}%` : "0%",
            background: warn ? "var(--color-warning)" : "var(--color-primary)",
          }}
        />
      </div>
      {warn && warnText && (
        <p className="mt-1.5 inline-flex items-center gap-1.5 text-tiny font-medium text-warning">
          <AlertTriangle className="size-3.5" strokeWidth={2} aria-hidden="true" />
          {warnText}
        </p>
      )}
    </div>
  );
}

/** Big headline number that counts up, with a muted unit: "72%" */
export function HeroNumber({ value, unit = "%", className = "" }) {
  const shown = useCountUp(value);
  return (
    <span className={`tabular font-[family-name:var(--font-latin-first)] font-light leading-none text-text ${className}`}>
      {Math.round(shown)}
      <span className="ml-0.5 text-[0.5em] text-text-muted">{unit}</span>
    </span>
  );
}
