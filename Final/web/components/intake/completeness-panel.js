"use client";

import { useEffect, useId, useState } from "react";
import { Check, Circle, Sparkles } from "lucide-react";
import { Button, ErrorState } from "@/components/intake/ui";
import { ProfileChangesNote } from "@/components/app/profile-changes";

// Progress sidebar / completeness meter (DesignSystem.md section 3, FR-9, FR-14):
// score with a bar, slot checklist with required slots first, what to add next,
// CV and questionnaire marked "ไม่บังคับ" when skipped (never red), and the
// "สร้างโปรไฟล์" button enabled only when `can_generate`.

export const THRESHOLD = 65;

export const SLOT_LABELS = {
  hard_skills: "ทักษะด้านเทคนิค ≥ 3 พร้อมระดับ",
  experience: "ประสบการณ์ / ยังไม่มี",
  soft_skills: "ทักษะการทำงานร่วมกับผู้อื่น",
  goals: "เป้าหมายสายงาน",
  work_style: "ความชอบในการทำงาน",
  education: "การศึกษา",
};

const INPUT_TEXT = {
  cv: { done: "CV · ยืนยันแล้ว", skipped: "CV · ไม่บังคับเมื่อทำแบบสอบถาม" },
  questionnaire: {
    done: "แบบสอบถาม · ครบแล้ว",
    partial: "แบบสอบถาม · ทำไปบางส่วน",
    skipped: "แบบสอบถาม · ไม่บังคับเมื่อมี CV",
  },
};

function ScoreBar({ score }) {
  const pass = score >= THRESHOLD;
  return (
    <div>
      <p className="flex items-end gap-2">
        <span className="tabular font-[family-name:var(--font-latin-first)] text-[44px] leading-none font-semibold text-text">
          {score}
          <span className="text-h3 text-text-muted">%</span>
        </span>
        {pass && (
          <span className="mb-1 inline-flex items-center gap-1 rounded-full bg-primary-subtle px-2 py-0.5 text-tiny font-medium text-text">
            <Check className="size-3.5 text-success" strokeWidth={3} aria-hidden="true" />
            ถึงเกณฑ์แล้ว
          </span>
        )}
      </p>
      <div
        role="progressbar"
        aria-label="ความครบถ้วนของข้อมูล"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
        className="relative mt-4 h-2.5 overflow-visible rounded-full bg-border"
      >
        <div className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out" style={{ width: `${score}%` }} />
        {/* threshold marker */}
        <span className="absolute -top-1 h-4.5 w-0.5 rounded-full bg-text-muted" style={{ left: `${THRESHOLD}%` }} aria-hidden="true" />
      </div>
      <p className="mt-1.5 text-tiny text-text-muted" style={{ paddingLeft: `calc(${THRESHOLD}% - 1.5rem)` }}>
        เกณฑ์ {THRESHOLD}%
      </p>
    </div>
  );
}

function SlotList({ slots }) {
  const ordered = [...slots].sort((a, b) => Number(b.required) - Number(a.required) || b.max_points - a.max_points);
  return (
    <ul className="space-y-2.5">
      {ordered.map((s) => (
        <li key={s.slot} className="flex items-start gap-2.5 text-small">
          {s.filled ? (
            <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-success text-bg">
              <Check className="size-3.5" strokeWidth={3} aria-hidden="true" />
            </span>
          ) : (
            <Circle className="mt-0.5 size-5 shrink-0 text-border" strokeWidth={2} aria-hidden="true" />
          )}
          <span className={`flex-1 ${s.filled ? "text-text" : "text-text-muted"}`}>
            {SLOT_LABELS[s.slot] ?? s.slot}
            <span className="sr-only">{s.filled ? " (ครบแล้ว)" : " (ยังไม่ครบ)"}</span>
          </span>
          {s.required && (
            <span className={`rounded-full px-2 text-tiny font-medium ${s.filled ? "bg-primary-subtle text-text" : "border border-warning text-warning"}`}>
              จำเป็น
            </span>
          )}
          <span className="tabular w-10 text-right text-tiny text-text-muted">+{s.max_points}</span>
        </li>
      ))}
    </ul>
  );
}

export function CompletenessPanel({ completeness, error, onRetry, onGenerate, generating, generateError }) {
  const reasonId = useId();
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!generating) return undefined;
    const id = setTimeout(() => setSlow(true), 5000);
    return () => {
      clearTimeout(id);
      setSlow(false);
    };
  }, [generating]);

  if (error) return <ErrorState error={error} onRetry={onRetry} compact />;
  if (!completeness) {
    return (
      <div className="space-y-4" aria-hidden="true">
        <div className="h-11 w-24 animate-pulse rounded-md bg-border/60" />
        <div className="h-2.5 animate-pulse rounded-full bg-border/60" />
        <div className="h-32 animate-pulse rounded-md bg-border/60" />
      </div>
    );
  }

  const { score, can_generate, slots, missing_required, missing_th, inputs, profile_changes: changes } = completeness;
  const missingRequiredLabels = missing_required.map((s) => SLOT_LABELS[s] ?? s);
  const reason = !can_generate
    ? missingRequiredLabels.length
      ? `ยังขาดข้อมูลจำเป็น: ${missingRequiredLabels.join(" และ ")}`
      : score < THRESHOLD
        ? `ต้องได้อย่างน้อย ${THRESHOLD}% (ตอนนี้ ${score}%)`
        : "อัปโหลด CV หรือทำแบบสอบถามอย่างน้อยหนึ่งอย่าง"
    : null;

  return (
    <div className="space-y-6">
      <ScoreBar score={score} />
      <SlotList slots={slots} />

      <ul className="space-y-1 border-t border-border pt-4 text-small text-text-muted">
        <li>{INPUT_TEXT.cv[inputs.cv]}</li>
        <li>{INPUT_TEXT.questionnaire[inputs.questionnaire]}</li>
      </ul>

      {missing_th.length > 0 && (
        <div>
          <p className="text-small font-semibold text-text">เพิ่มต่อได้</p>
          <ul className="mt-2 space-y-1.5 text-small text-text-muted">
            {missing_th.slice(0, 3).map((m) => (
              <li key={m} className="flex gap-2">
                <span aria-hidden="true">•</span>
                {m}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-2">
        <ProfileChangesNote changes={changes} />
        <Button
          className="w-full"
          disabled={!can_generate}
          loading={generating}
          onClick={onGenerate}
          aria-describedby={reason ? reasonId : undefined}
        >
          {!generating && <Sparkles className="size-4" strokeWidth={1.75} aria-hidden="true" />}
          {can_generate ? "สร้างโปรไฟล์" : "เพิ่มข้อมูลก่อนสร้างโปรไฟล์"}
        </Button>
        {reason && (
          <p id={reasonId} className="text-tiny text-text-muted">
            {reason}
          </p>
        )}
        {generating && slow && (
          <p role="status" className="text-tiny text-text-muted">
            กำลังวิเคราะห์ อาจใช้เวลาสักครู่
          </p>
        )}
        <ErrorState error={generateError} compact />
      </div>

      <p className="text-tiny text-text-muted">เกณฑ์ {THRESHOLD}% และข้อมูลจำเป็นครบ · ข้อมูลบันทึกให้อัตโนมัติ</p>
    </div>
  );
}
