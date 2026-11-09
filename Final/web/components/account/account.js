"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { RotateCcw, Trash2 } from "lucide-react";
import { data } from "@/lib/data";
import { usePageReady } from "@/components/motion/page-transition";
import { dateTh } from "@/lib/format";
import { useSession } from "@/lib/session";
import { Button, Card, ErrorState, LoadingBlock } from "@/components/intake/ui";

// Account page /account (DesignSystem.md section 4, FR-25, FR-29, FR-35): email,
// today's quota and reset time, removed skills (restore), and delete all data
// after typing "DELETE" in a dialog. No step indicator: it is not a step.

const THEME_TH = { light: "สว่าง", dark: "มืด", system: "ตามระบบ" };
const timeTh = (iso) => new Date(iso).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" });

function QuotaCard({ quota }) {
  if (!quota) return <Card title="โควตาวันนี้"><LoadingBlock lines={2} /></Card>;
  const left = Math.max(0, quota.requests_limit - quota.requests_used);
  const pct = Math.min(100, Math.round((quota.requests_used / quota.requests_limit) * 100));
  const low = quota.exhausted || left / quota.requests_limit < 0.2;
  return (
    <Card title="โควตาวันนี้" subtitle="จำนวนครั้งที่ถาม AI ได้ต่อวัน">
      <p className="tabular font-[family-name:var(--font-latin-first)] text-h1 font-semibold text-text">
        {quota.requests_used} / {quota.requests_limit} <span className="text-h3 font-normal">ครั้ง</span>
      </p>
      <div
        role="progressbar"
        aria-label="โควตาที่ใช้ไปวันนี้"
        aria-valuemin={0}
        aria-valuemax={quota.requests_limit}
        aria-valuenow={quota.requests_used}
        className="mt-3 h-2.5 overflow-hidden rounded-full bg-border"
      >
        <div className={`h-full rounded-full ${low ? "bg-warning" : "bg-primary"}`} style={{ width: `${pct}%` }} />
      </div>
      <p className={`mt-3 text-small ${low ? "font-semibold text-warning" : "text-text"}`}>
        {quota.exhausted ? "ใช้ AI ครบแล้ววันนี้" : `เหลือ ${left} ครั้ง`}
      </p>
      <p className="text-small text-text-muted">
        รีเซ็ต {dateTh(quota.reset_at)} {timeTh(quota.reset_at)} น.
      </p>
      <p className="mt-2 text-tiny text-text-muted">การลบหรือกู้คืนทักษะไม่ใช้โควตา</p>
    </Card>
  );
}

function DeleteDialog({ open, onClose }) {
  const ref = useRef(null);
  const inputRef = useRef(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const hintId = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      inputRef.current?.focus();
    } else if (!open && d.open) d.close();
  }, [open]);

  function cancel() {
    if (busy) return;
    setText("");
    setError(null);
    onClose();
  }

  async function submit(e) {
    e.preventDefault();
    if (text !== "DELETE") return;
    setBusy(true);
    setError(null);
    try {
      await data.deleteMe({ confirm: "DELETE" });
      // The session cookie is cleared; a full load drops every cached page state.
      window.location.replace("/");
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="delete-title"
      onCancel={(e) => {
        e.preventDefault();
        cancel();
      }}
      className="m-auto w-[min(30rem,calc(100vw-2rem))] rounded-xl border border-border bg-surface p-0 text-text shadow-xl backdrop:bg-black/40"
    >
      <form onSubmit={submit} className="p-6">
        <h2 id="delete-title" className="text-h3 font-semibold text-text">
          ลบบัญชีและข้อมูลทั้งหมด
        </h2>
        <p className="mt-2 text-small text-text-muted">
          ระบบจะลบ CV คำตอบแบบสอบถาม ประวัติแชท โปรไฟล์ ทักษะที่ลบไว้ และข้อมูลการใช้งานของคุณทั้งหมด การดำเนินการนี้ยกเลิกไม่ได้
        </p>
        <label htmlFor="delete-confirm" className="mt-5 block text-small font-semibold text-text">
          พิมพ์ DELETE เพื่อยืนยัน
        </label>
        <input
          id="delete-confirm"
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          aria-describedby={hintId}
          className="mt-1.5 block w-full rounded-sm border border-border bg-bg px-3 py-2.5 font-[family-name:var(--font-latin-first)] text-body text-text focus:border-primary focus:outline-2 focus:outline-primary/30"
        />
        <p id={hintId} className="mt-1 text-tiny text-text-muted">
          ต้องพิมพ์ตัวพิมพ์ใหญ่ให้ตรงทุกตัว
        </p>
        {error && (
          <div className="mt-3">
            <ErrorState error={error} compact />
          </div>
        )}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={cancel} disabled={busy}>
            ยกเลิก
          </Button>
          <Button type="submit" variant="danger" loading={busy} disabled={text !== "DELETE"}>
            ลบอย่างถาวร
          </Button>
        </div>
      </form>
    </dialog>
  );
}

export function Account() {
  const session = useSession();
  const { theme } = useTheme();
  const [removed, setRemoved] = useState(null);
  const [removedError, setRemovedError] = useState(null);
  const [restoring, setRestoring] = useState(null);
  const [restoreError, setRestoreError] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const loadRemoved = useCallback(
    () =>
      data.removedSkills().then(
        (r) => {
          setRemovedError(null);
          setRemoved(r.skills);
        },
        (e) => (e.code === "PROFILE_NOT_FOUND" ? setRemoved([]) : setRemovedError(e)),
      ),
    [],
  );

  useEffect(() => {
    if (session.status === "ready") loadRemoved();
  }, [session.status, loadRemoved]);
  usePageReady(session.status === "ready" || session.status === "error");

  async function restore(skill) {
    setRestoring(skill.skill_id);
    setRestoreError(null);
    try {
      await data.restoreSkill(skill.skill_id);
      setRemoved((list) => list.filter((s) => s.skill_id !== skill.skill_id));
    } catch (e) {
      setRestoreError(e);
    } finally {
      setRestoring(null);
    }
  }

  const wrap = (children) => <div className="mx-auto w-full max-w-[1120px] px-4 pt-8 pb-24 md:px-6 md:pt-10">{children}</div>;
  if (session.status === "error") return wrap(<ErrorState error={session.error} onRetry={() => window.location.reload()} />);
  if (session.status !== "ready") return wrap(<LoadingBlock lines={6} label="กำลังโหลดบัญชี…" />);

  const { user, quota } = session;

  return wrap(
    <>
      <header>
        <h1 className="text-h1 font-bold text-text">บัญชีและข้อมูลของคุณ</h1>
        <p className="mt-1 text-body text-text-muted">ควบคุมข้อมูลส่วนตัว การใช้งาน และทักษะที่เคยลบ</p>
      </header>

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card title="ข้อมูลบัญชี">
          <dl className="grid gap-x-6 gap-y-3 text-small sm:grid-cols-[max-content_1fr]">
            <dt className="text-text-muted">ชื่อที่แสดง</dt>
            <dd className="text-text">{user.display_name}</dd>
            <dt className="text-text-muted">อีเมล</dt>
            <dd className="font-[family-name:var(--font-latin-first)] break-all text-text">{user.email}</dd>
            <dt className="text-text-muted">สมัครเมื่อ</dt>
            <dd className="text-text">{dateTh(user.created_at)}</dd>
            <dt className="text-text-muted">ธีม</dt>
            <dd className="text-text">
              {THEME_TH[theme] ?? "ตามระบบ"} <span className="text-text-muted">· เปลี่ยนได้จากปุ่มธีมด้านบน (บันทึกในเบราว์เซอร์นี้เท่านั้น)</span>
            </dd>
          </dl>
        </Card>
        <QuotaCard quota={quota} />
      </div>

      <div className="mt-6 space-y-6">
        <Card title="ทักษะที่คุณลบออก" subtitle="ไม่นำมาใช้คำนวณสายงาน · กู้คืนได้ทุกเมื่อ และไม่ใช้โควตา AI">
          {removedError ? (
            <ErrorState error={removedError} onRetry={loadRemoved} compact />
          ) : removed === null ? (
            <LoadingBlock lines={2} />
          ) : removed.length === 0 ? (
            <p className="text-small text-text-muted">ยังไม่มีทักษะที่ลบไว้</p>
          ) : (
            <ul className="divide-y divide-border">
              {removed.map((s) => (
                <li key={s.skill_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <span className="font-semibold text-text">{s.name_th}</span>
                  <span className="text-small text-text-muted">ลบเมื่อ {dateTh(s.removed_at)}</span>
                  <Button variant="secondary" onClick={() => restore(s)} loading={restoring === s.skill_id} disabled={Boolean(restoring)}>
                    {restoring !== s.skill_id && <RotateCcw className="size-4" strokeWidth={2} aria-hidden="true" />}
                    กู้คืน
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {restoreError && (
            <div className="mt-3">
              <ErrorState error={restoreError} compact />
            </div>
          )}
        </Card>

        <Card title="ลบข้อมูลทั้งหมด" className="border-danger/40">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <p className="max-w-xl text-small text-text">
              ลบบัญชี โปรไฟล์ ประวัติแชท และข้อมูลทั้งหมดของคุณอย่างถาวร คุณจะต้องพิมพ์ DELETE เพื่อยืนยัน
            </p>
            <Button variant="danger" onClick={() => setDeleting(true)}>
              <Trash2 className="size-4" strokeWidth={2} aria-hidden="true" />
              ลบบัญชีและข้อมูล
            </Button>
          </div>
        </Card>
      </div>

      <DeleteDialog open={deleting} onClose={() => setDeleting(false)} />
    </>,
  );
}
