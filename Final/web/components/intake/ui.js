"use client";

import { useId } from "react";
import { AlertCircle, Loader2, RotateCcw } from "lucide-react";

// Small building blocks for the intake page (DesignSystem.md section 3).

export const LEVELS = [
  { value: 1, label: "เริ่มต้น" },
  { value: 2, label: "ใช้งานได้" },
  { value: 3, label: "คล่อง" },
  { value: 4, label: "เชี่ยวชาญ" },
];
export const levelLabel = (level) => LEVELS.find((l) => l.value === level)?.label;

export function Card({ title, subtitle, actions, children, className = "", ...props }) {
  return (
    <section className={`rounded-xl border border-border bg-glass p-5 shadow-sm md:p-6 ${className}`} {...props}>
      {(title || actions) && (
        <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-h3 font-semibold text-text">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-small text-text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

const VARIANTS = {
  primary: "bg-primary text-on-primary hover:bg-primary-hover shadow-sm",
  secondary: "border border-border bg-bg text-text hover:border-primary",
  ghost: "text-text hover:bg-bg",
  danger: "border border-danger/50 bg-bg text-danger hover:bg-danger hover:text-on-primary",
};

export function Button({ variant = "primary", loading = false, className = "", children, disabled, ...props }) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-4 text-small font-semibold transition-colors duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-60 ${VARIANTS[variant]} ${className}`}
      {...props}
    >
      {loading && <Loader2 className="size-4 animate-spin" strokeWidth={2} aria-hidden="true" />}
      {children}
    </button>
  );
}

/** Error state (DesignSystem.md 3): message_th, retry, and a copyable request id. */
export function ErrorState({ error, onRetry, compact = false }) {
  if (!error) return null;
  return (
    <div role="alert" className={`flex items-start gap-3 rounded-md border border-danger/40 bg-bg ${compact ? "p-3" : "p-4"}`}>
      <AlertCircle className="mt-0.5 size-5 shrink-0 text-danger" strokeWidth={2} aria-hidden="true" />
      <div className="min-w-0 flex-1 text-small">
        <p className="text-text">{error.messageTh || error.message || "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง"}</p>
        {error.requestId && (
          <p className="mt-1 text-tiny text-text-muted">
            รหัสอ้างอิง: <span className="font-[family-name:var(--font-latin-first)] select-all">{error.requestId}</span>
          </p>
        )}
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-md px-2 text-small font-semibold text-accent hover:bg-surface">
          <RotateCcw className="size-4" strokeWidth={2} aria-hidden="true" />
          ลองใหม่
        </button>
      )}
    </div>
  );
}

export function Skeleton({ lines = 4 }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-12 animate-pulse rounded-md bg-border/60" style={{ width: `${100 - (i % 3) * 12}%` }} />
      ))}
    </div>
  );
}

export function LoadingBlock({ label = "กำลังโหลด…", lines }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <Skeleton lines={lines} />
    </div>
  );
}

/** Skill level 1-4 as a segmented radio group ("ระดับ 1 เริ่มต้น → 4 เชี่ยวชาญ"). */
export function LevelPicker({ value, onChange, label, size = "md" }) {
  const name = useId();
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-border bg-bg p-0.5">
      {LEVELS.map((l) => {
        const checked = value === l.value;
        return (
          <label
            key={l.value}
            title={`ระดับ ${l.value} · ${l.label}`}
            className={`relative flex cursor-pointer items-center justify-center rounded-sm text-tiny font-semibold transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary ${
              size === "sm" ? "min-h-8 min-w-8 px-2" : "min-h-10 min-w-10 px-3"
            } ${checked ? "bg-primary text-on-primary" : "text-text-muted hover:bg-surface hover:text-text"}`}
          >
            <input
              type="radio"
              name={name}
              value={l.value}
              checked={checked}
              onChange={() => onChange(l.value)}
              className="sr-only"
            />
            <span aria-hidden="true">{l.value}</span>
            <span className="sr-only">{`ระดับ ${l.value} ${l.label}`}</span>
          </label>
        );
      })}
    </div>
  );
}

/** Level shown as 4 dots (DesignSystem.md: skill chip level dots). */
export function LevelDots({ level }) {
  return (
    <span className="inline-flex gap-1" aria-hidden="true">
      {LEVELS.map((l) => (
        <span key={l.value} className={`size-1.5 rounded-full ${level >= l.value ? "bg-primary" : "bg-border"}`} />
      ))}
    </span>
  );
}
