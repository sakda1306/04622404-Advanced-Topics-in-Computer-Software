"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Check, Clock, RotateCcw, X } from "lucide-react";
import { data } from "@/lib/data";
import { baht } from "@/lib/format";
import { Button, ErrorState } from "@/components/intake/ui";

// Edit proposal card (DesignSystem.md section 3, FR-27, FR-31): shows each
// change as "เดิม → ใหม่", ยืนยัน / ยกเลิก, and expires 15 minutes after it was
// made (`expires_at`): then it greys out with "หมดเวลา กรุณาพิมพ์คำขออีกครั้ง".
// Nothing changes in the profile until the user confirms.

const SKILL_LEVEL = { 1: "เริ่มต้น", 2: "ใช้งานได้", 3: "คล่อง", 4: "เชี่ยวชาญ" };
const WORK_STYLE = {
  teamwork: "การทำงานกับทีม",
  structure: "ความชอบขั้นตอนชัดเจน",
  ambiguity: "ความชอบโจทย์ปลายเปิด",
  pressure: "ความชอบงานเร่งด่วน",
  innovation: "ความชอบวิธีใหม่ ๆ",
  leadership: "ความชอบบทบาทผู้นำ",
};

function fieldLabel(c) {
  if (c.field === "preferences.desired_salary_thb") return "เงินเดือนที่ต้องการ";
  if (c.field === "preferences.interested_roles") return "สายงานที่สนใจ";
  if (c.field === "preferences.locations") return "พื้นที่ทำงาน";
  if (c.field.startsWith("preferences.work_style.")) return WORK_STYLE[c.field.split(".").pop()] ?? "รูปแบบการทำงาน";
  if (c.field.endsWith(".years")) return `ประสบการณ์ ${c.skill_id}`;
  if (c.field.endsWith(".level")) return "ระดับทักษะ";
  return "ทักษะ";
}

function valueText(c, value) {
  if (value === null || value === undefined || value === "") return "ไม่มี";
  if (c.field === "preferences.desired_salary_thb") return `${baht(value)} / เดือน`;
  if (c.field.endsWith(".level")) return `ระดับ ${value} ${SKILL_LEVEL[value] ?? ""}`.trim();
  if (c.field.endsWith(".years")) return `${value} ปี`;
  if (c.field.startsWith("preferences.work_style.")) return `${Math.round(value * 100)} / 100`;
  if (Array.isArray(value)) return value.join(", ") || "ไม่มี";
  if (typeof value === "object") return [value.name_th, value.level ? `ระดับ ${value.level}` : ""].filter(Boolean).join(" ");
  return String(value);
}

function ChangeRow({ change }) {
  const skill = change.new_value?.name_th ?? change.old_value?.name_th;
  const title =
    change.op === "add"
      ? change.restores_removed_skill
        ? "เพิ่มทักษะที่คุณเคยลบกลับมา"
        : "เพิ่มทักษะ"
      : change.op === "remove"
        ? "ลบทักษะ"
        : `${fieldLabel(change)}${change.field.endsWith(".level") && change.skill_id ? ` · ${skill ?? change.skill_id}` : ""}`;
  return (
    <li className="rounded-md border border-border bg-surface px-3 py-2">
      <p className="text-tiny font-semibold text-text-muted">{title}</p>
      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-small text-text">
        {change.op === "add" ? (
          <span className="font-semibold">{valueText(change, change.new_value)}</span>
        ) : change.op === "remove" ? (
          <span className="line-through decoration-danger/70">{valueText(change, change.old_value)}</span>
        ) : (
          <>
            <span className="text-text-muted">{valueText(change, change.old_value)}</span>
            <ArrowRight className="size-3.5 text-text-muted" strokeWidth={2} aria-label="เป็น" />
            <span className="font-semibold">{valueText(change, change.new_value)}</span>
          </>
        )}
      </p>
      {change.restores_removed_skill && <p className="mt-1 text-tiny text-info">ทักษะนี้จะกลับมาใช้คำนวณสายงานอีกครั้ง</p>}
    </li>
  );
}

/** Minutes left until `expiresAt`, re-checked every 15 s; null until mounted. */
function useMinutesLeft(expiresAt) {
  const [left, setLeft] = useState(null);
  useEffect(() => {
    const tick = () => setLeft(Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 60000)));
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, 15000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [expiresAt]);
  return left;
}

/**
 * @param {object} props
 * @param {object} props.edit  EditProposal
 * @param {(result: {profile, matches}) => void} [props.onApplied]
 */
export function EditProposalCard({ edit, onApplied }) {
  const [status, setStatus] = useState(edit.status);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [failed, setFailed] = useState(null); // what the retry repeats: a cancel must never confirm
  const left = useMinutesLeft(edit.expires_at);
  const expired = status === "expired" || (status === "pending" && left === 0);

  async function act(kind) {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "confirm") {
        const result = await data.confirmEdit(edit.edit_id);
        setStatus("applied");
        onApplied?.(result);
      } else {
        await data.rejectEdit(edit.edit_id);
        setStatus("rejected");
      }
    } catch (e) {
      if (e.code === "EDIT_EXPIRED") setStatus("expired");
      else if (e.code === "EDIT_NOT_FOUND") setStatus("rejected");
      else {
        setFailed(kind);
        setError(e);
      }
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      className={`mt-2 rounded-lg border p-4 ${expired || status === "rejected" ? "border-border bg-glass opacity-70" : "border-primary/40 bg-glass"}`}
      aria-label="ข้อเสนอแก้ไขโปรไฟล์"
      role="group"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-small font-semibold text-text">ยืนยันการแก้ไขโปรไฟล์</p>
        {status === "pending" && !expired && (
          <span className="inline-flex items-center gap-1 text-tiny text-text-muted">
            <Clock className="size-3.5" strokeWidth={2} aria-hidden="true" />
            ยืนยันได้ภายใน 15 นาที{left !== null && left < 15 ? ` · เหลือ ${left} นาที` : ""}
          </span>
        )}
      </div>
      <ul className="mt-3 space-y-2">
        {edit.changes.map((c, i) => (
          <ChangeRow key={i} change={c} />
        ))}
      </ul>

      {error && (
        <div className="mt-3">
          <ErrorState error={error} compact onRetry={error.code === "EDIT_CONFLICT" ? undefined : () => act(failed)} />
        </div>
      )}

      {status === "applied" ? (
        <p role="status" className="mt-3 inline-flex items-center gap-1.5 text-small font-semibold text-success">
          <Check className="size-4" strokeWidth={2.5} aria-hidden="true" />
          แก้ไขโปรไฟล์แล้ว · คำนวณสายงานใหม่ให้แล้ว
        </p>
      ) : status === "rejected" ? (
        <p role="status" className="mt-3 inline-flex items-center gap-1.5 text-small text-text-muted">
          <X className="size-4" strokeWidth={2} aria-hidden="true" />
          ยกเลิกแล้ว ข้อมูลในโปรไฟล์ไม่เปลี่ยน
        </p>
      ) : expired ? (
        <p role="status" className="mt-3 inline-flex items-center gap-1.5 text-small text-text-muted">
          <RotateCcw className="size-4" strokeWidth={2} aria-hidden="true" />
          หมดเวลา กรุณาพิมพ์คำขออีกครั้ง
        </p>
      ) : (
        <>
          <p className="mt-3 text-tiny text-text-muted">ข้อมูลเดิมจะเปลี่ยนหลังคุณยืนยันเท่านั้น</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button onClick={() => act("confirm")} loading={busy === "confirm"} disabled={Boolean(busy)}>
              ยืนยัน
            </Button>
            <Button variant="secondary" onClick={() => act("reject")} loading={busy === "reject"} disabled={Boolean(busy)}>
              ยกเลิก
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
