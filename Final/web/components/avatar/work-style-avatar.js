"use client";

import { useId, useMemo } from "react";
import {
  AVATAR_TRAITS,
  answeredCount,
  avatarLabelTh,
  avatarSvg,
  avatarSwatch,
  reasonTh,
} from "@/lib/avatar";

// Work-style avatar (docs/WorkStyleAvatar.md). The markup comes from lib/avatar.js,
// which builds it from fixed shapes only (no user text), so it is injected as is.
// Idle motion: the body breathes and the eyes blink; globals.css turns it off for
// prefers-reduced-motion.

/** `delay` (seconds) offsets the motion so several avatars on one page do not move in step. */
export function WorkStyleAvatar({ steps, size = 160, animate = true, doodle = true, decorative = false, delay = 0, className = "" }) {
  const rawId = useId();
  const id = `wsa${rawId.replace(/[^a-zA-Z0-9]/g, "")}`;
  const markup = useMemo(
    () => avatarSvg(steps, { id, doodle, label: decorative ? "" : avatarLabelTh(steps) }),
    [steps, id, doodle, decorative],
  );
  return (
    <span
      className={`wsa inline-block shrink-0 ${animate ? "wsa-animate" : ""} ${className}`}
      style={{ width: size, height: (size * 260) / 240, "--wsa-delay": `${delay}s` }}
      dangerouslySetInnerHTML={{ __html: markup }}
    />
  );
}

/**
 * One line per part: the variant and the answer behind it (section 5 of the proposal).
 * `cite(traitKey)` may return a citation node for that trait.
 */
export function AvatarExplain({ steps, cite, className = "" }) {
  return (
    <ul className={`divide-y divide-border ${className}`}>
      {AVATAR_TRAITS.map((t) => {
        const step = steps?.[t.key] ?? null;
        return (
          <li key={t.key} className="grid grid-cols-[88px_1fr] gap-3 py-2 text-small">
            <span className="text-text-muted">{t.part_th}</span>
            <span className="text-text">
              {step == null ? (
                <span className="text-text-muted">ยังไม่มีคำตอบ</span>
              ) : (
                <>
                  {t.key === "pressure" && (
                    <span
                      className="mr-1.5 inline-block size-3 rounded-full border border-text/70 align-[-1px]"
                      style={{ background: avatarSwatch(step) }}
                      aria-hidden="true"
                    />
                  )}
                  <span className="font-medium">{t.names_th[step - 1]}</span>
                  <span className="text-text-muted"> · {reasonTh(t, step)}</span>
                  {cite?.(t.key)}
                </>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** "ยังตอบไม่ครบ · X/6 ข้อ" when any answer is missing, otherwise nothing. */
export function AvatarProgress({ steps, className = "" }) {
  const done = answeredCount(steps ?? {});
  if (done === AVATAR_TRAITS.length) return null;
  return (
    <p className={`text-small text-text-muted ${className}`}>
      ยังตอบไม่ครบ · <span className="tabular">{done}/{AVATAR_TRAITS.length}</span> ข้อ
    </p>
  );
}

export const AVATAR_CAPTION_TH = "ตัวละครจากความชอบในการทำงานของคุณ";
export const AVATAR_DISCLAIMER_TH = "ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ";
