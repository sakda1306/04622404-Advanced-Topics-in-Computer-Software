"use client";

import { PencilLine, X } from "lucide-react";
import { Cite } from "@/components/app/citation";
import { LevelDots, levelLabel } from "@/components/intake/ui";

// Skill chip (DesignSystem.md section 3, FR-29, FR-33): name, level dots, the
// evidence citations, "แก้ไขโดยคุณ" when the user changed it, and a remove
// button (44 px hit target) that asks the parent to confirm before removing.
export function SkillChip({ skill, onRemove, disabled = false, className = "", style }) {
  const level = levelLabel(skill.level);
  return (
    <li className={`inline-flex min-h-11 items-center gap-2 rounded-full border border-border bg-bg py-1 pr-1 pl-4 text-small text-text ${className}`} style={style}>
      <span className="font-semibold">{skill.name_th}</span>
      <span className="inline-flex items-center gap-1.5" title={`ระดับ ${skill.level} · ${level}`}>
        <LevelDots level={skill.level} />
        <span className="sr-only">{`ระดับ ${skill.level} ${level}`}</span>
      </span>
      {skill.years ? <span className="text-tiny text-text-muted tabular">{skill.years} ปี</span> : null}
      {skill.edited_by_user && (
        <span className="inline-flex items-center gap-1 rounded-full bg-primary-subtle px-2 py-0.5 text-tiny font-medium text-text">
          <PencilLine className="size-3" strokeWidth={2} aria-hidden="true" />
          แก้ไขโดยคุณ
        </span>
      )}
      <Cite ids={skill.evidence_ids} />
      {onRemove ? (
        <button
          type="button"
          onClick={() => onRemove(skill)}
          disabled={disabled}
          aria-label={`ลบทักษะ ${skill.name_th}`}
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-full text-text-muted transition-colors duration-150 hover:bg-surface hover:text-danger disabled:opacity-50 before:absolute before:size-11 relative"
        >
          <X className="size-4" strokeWidth={2} aria-hidden="true" />
        </button>
      ) : (
        <span className="pr-3" />
      )}
    </li>
  );
}
