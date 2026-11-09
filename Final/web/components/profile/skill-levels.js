"use client";

import { useId } from "react";
import { Rocket, Sprout, Trophy, Wrench } from "lucide-react";
import { LEVELS } from "@/components/intake/ui";
import { SkillChip } from "@/components/profile/skill-chip";

// Skills grouped by level, 4 (เชี่ยวชาญ) down to 1 (เริ่มต้น); a level with no
// skills is not shown. A summary bar on top gives each level's share and jumps to
// its group. Level is always said in text too (heading, chip dots + label), never
// by tint alone. Chips fade in one after another once, when the card appears.

const LEVEL_ICONS = { 4: Trophy, 3: Rocket, 2: Wrench, 1: Sprout };
// Tint strength per level: the higher the level, the stronger the colour.
const LEVEL_TINT = { 4: 100, 3: 72, 2: 48, 1: 28 };
const STAGGER_MS = 40;

/** Colour of the card: technical skills in Accent, teamwork skills in Info. */
const TONES = { tech: "var(--color-accent)", team: "var(--color-info)" };
const tint = (tone, pct) => `color-mix(in oklab, ${TONES[tone]} ${pct}%, transparent)`;

export function SkillLevels({ skills, tone = "tech", onRemove, busy, label }) {
  const baseId = useId();
  const groups = [...LEVELS]
    .reverse()
    .map((l) => ({ ...l, skills: skills.filter((s) => s.level === l.value) }))
    .filter((g) => g.skills.length);
  const groupId = (level) => `${baseId}-level-${level}`;
  let order = 0;

  return (
    <div>
      <div className="mb-5">
        <div className="flex h-2.5 overflow-hidden rounded-full bg-border" aria-hidden="true">
          {groups.map((g) => (
            <span key={g.value} className="h-full first:rounded-l-full last:rounded-r-full" style={{ width: `${(g.skills.length / skills.length) * 100}%`, background: tint(tone, LEVEL_TINT[g.value]) }} />
          ))}
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-1 gap-y-1" aria-label={`สัดส่วน${label}ตามระดับ`}>
          {groups.map((g) => (
            <li key={g.value}>
              <a
                href={`#${groupId(g.value)}`}
                data-transition="off"
                className="inline-flex min-h-8 items-center gap-1.5 rounded-md px-2 text-tiny text-text-muted transition-colors duration-150 hover:bg-bg hover:text-text"
              >
                <span className="size-2.5 rounded-full" style={{ background: tint(tone, LEVEL_TINT[g.value]) }} aria-hidden="true" />
                {g.value} {g.label}
                <span className="tabular font-semibold text-text">{g.skills.length}</span>
              </a>
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-3">
        {groups.map((g) => {
          const Icon = LEVEL_ICONS[g.value];
          return (
            <section
              key={g.value}
              id={groupId(g.value)}
              aria-labelledby={`${groupId(g.value)}-title`}
              className="scroll-mt-28 rounded-lg border-l-4 p-3 md:p-4"
              style={{ borderColor: tint(tone, LEVEL_TINT[g.value]), background: tint(tone, 6) }}
            >
              <header className="mb-3 flex items-center gap-2.5">
                <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full" style={{ background: tint(tone, 16), color: TONES[tone] }}>
                  <Icon className="size-4.5" strokeWidth={2} aria-hidden="true" />
                </span>
                <h3 id={`${groupId(g.value)}-title`} className="text-small font-semibold text-text">
                  ระดับ {g.value} · {g.label}
                </h3>
                <span className="tabular ml-auto rounded-full bg-surface px-2 py-0.5 text-tiny font-semibold text-text-muted">{g.skills.length} ทักษะ</span>
              </header>
              <ul className="flex flex-wrap gap-2" aria-label={`${label} ระดับ ${g.value} ${g.label}`}>
                {g.skills.map((s) => (
                  <SkillChip key={s.skill_id} skill={s} onRemove={onRemove} disabled={busy} className="chip-in" style={{ animationDelay: `${order++ * STAGGER_MS}ms` }} />
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
