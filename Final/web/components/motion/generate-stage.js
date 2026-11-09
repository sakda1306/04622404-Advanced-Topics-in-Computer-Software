"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { WorkStyleAvatar } from "@/components/avatar/work-style-avatar";
import { AVATAR_TRAITS } from "@/lib/avatar";
import { useReducedMotion } from "@/lib/use-motion";

// "Generate profile" content for the transition panel: the user's work-style
// character is built in a mirror one part at a time (body, hair, face, colour,
// item, arms), with the real stages below it. The stages follow the request, never
// a timer: 0 = the generate request is running, 1 = the profile is saved and the
// profile page is loading.

const PART_MS = 260;

const STAGES = ["วิเคราะห์ CV แบบสอบถาม และแชทของคุณ", "เตรียมหน้าโปรไฟล์ของคุณ"];

/** Only the first `count` traits, so the character gains one part per tick. */
const partial = (steps, count) =>
  Object.fromEntries(AVATAR_TRAITS.map((t, i) => [t.key, i < count ? (steps?.[t.key] ?? null) : null]));

function StageRow({ label, state }) {
  const Icon = state === "done" ? CheckCircle2 : state === "active" ? Loader2 : Circle;
  return (
    <li className={`flex items-center gap-2.5 text-small ${state === "pending" ? "text-curtain-muted/70" : "text-curtain-fg"}`}>
      <Icon
        className={`size-4.5 shrink-0 ${state === "done" ? "text-curtain-accent" : ""} ${state === "active" ? "animate-spin motion-reduce:animate-none" : ""}`}
        strokeWidth={2}
        aria-hidden="true"
      />
      <span>
        {label}
        <span className="sr-only">{state === "done" ? " (เสร็จแล้ว)" : state === "active" ? " (กำลังทำ)" : ""}</span>
      </span>
    </li>
  );
}

/** @param {{stage: number, steps?: object}} props `steps`: the character's 1..5 per trait, when known. */
export function GenerateStage({ stage = 0, steps }) {
  const reduced = useReducedMotion();
  const [built, setBuilt] = useState(0);

  // One part per tick; restarts nothing when `steps` arrives later, the parts
  // already shown just take the real values.
  useEffect(() => {
    if (built >= AVATAR_TRAITS.length) return undefined;
    const t = setTimeout(() => setBuilt((n) => n + 1), reduced ? 0 : PART_MS);
    return () => clearTimeout(t);
  }, [built, reduced]);

  const shown = partial(steps, reduced ? AVATAR_TRAITS.length : built);
  const part = AVATAR_TRAITS[Math.min(built, AVATAR_TRAITS.length) - 1];

  return (
    <div className="flex flex-col items-center">
      <div className="gen-mirror relative flex size-52 items-center justify-center rounded-full md:size-60">
        <WorkStyleAvatar key={built} steps={shown} size={150} decorative className="gen-pop" />
      </div>
      <p className="mt-2 h-5 text-tiny text-curtain-muted" aria-hidden="true">
        {part && built < AVATAR_TRAITS.length ? `กำลังเติม${part.part_th}…` : "ตัวละครของคุณพร้อมแล้ว"}
      </p>

      <h2 className="mt-4 text-h2 font-bold text-curtain-fg">กำลังสร้างโปรไฟล์ของคุณ</h2>
      <ol className="mt-4 space-y-2 text-left" aria-busy="true">
        {STAGES.map((label, i) => (
          <StageRow key={label} label={label} state={stage > i ? "done" : stage === i ? "active" : "pending"} />
        ))}
      </ol>
    </div>
  );
}
