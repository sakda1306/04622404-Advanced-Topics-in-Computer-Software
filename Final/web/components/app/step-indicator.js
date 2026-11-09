import Link from "next/link";
import { Check, Lock } from "lucide-react";

// Step indicator (DesignSystem.md section 2, 4.1): always visible after login.
// Locked steps stay visible, disabled, with a Thai hint saying what unlocks them.

const STEPS = [
  { n: 1, label: "ข้อมูลของคุณ", href: "/start" },
  { n: 2, label: "โปรไฟล์", href: "/profile" },
  { n: 3, label: "สายงานที่เหมาะ", href: "/roles" },
  { n: 4, label: "รายละเอียดสายงาน", href: null },
];

const LOCK_HINT = "สร้างโปรไฟล์ในขั้นที่ 1 ก่อน เพื่อปลดล็อกขั้นนี้";

/** `current` is the active step number; `unlocked` is the furthest step that can be opened. */
export function StepIndicator({ current = 1, unlocked = 1 }) {
  return (
    <nav aria-label="ขั้นตอน" className="border-b border-border bg-surface">
      <ol className="mx-auto flex max-w-[1120px] gap-1 overflow-x-auto px-4 md:px-6">
        {STEPS.map(({ n, label, href }) => {
          const active = n === current;
          const done = n < current;
          const locked = n > unlocked;
          const badge = (
            <span
              className={`inline-flex size-6 shrink-0 items-center justify-center rounded-full text-tiny font-semibold tabular ${
                active ? "bg-primary text-on-primary" : done ? "bg-accent text-on-primary" : "border border-border text-text-muted"
              }`}
            >
              {done ? <Check className="size-3.5" strokeWidth={3} aria-hidden="true" /> : n}
            </span>
          );
          const body = (
            <>
              {badge}
              <span className="whitespace-nowrap">{label}</span>
              {locked && <Lock className="size-3.5 text-text-muted" strokeWidth={2} aria-hidden="true" />}
            </>
          );
          const base = "relative flex min-h-12 items-center gap-2 px-3 text-small";
          return (
            <li key={n} className="flex-1">
              {active ? (
                <span aria-current="step" className={`${base} font-semibold text-text`}>
                  {body}
                  <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-primary" aria-hidden="true" />
                </span>
              ) : locked || !href ? (
                <span aria-disabled="true" title={locked ? LOCK_HINT : undefined} className={`${base} cursor-not-allowed text-text-muted`}>
                  {body}
                  {locked && <span className="sr-only">{` (ล็อกอยู่: ${LOCK_HINT})`}</span>}
                </span>
              ) : (
                <Link href={href} className={`${base} rounded-md text-text hover:bg-bg`}>
                  {body}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
