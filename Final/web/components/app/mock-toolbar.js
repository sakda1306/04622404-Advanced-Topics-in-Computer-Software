"use client";

import { useId, useState, useSyncExternalStore } from "react";
import { FlaskConical, RotateCcw, X } from "lucide-react";
import { MOCK_DEFAULT, setMockOn, useMockMode } from "@/lib/mock/mode";
import { isMockAdmin, resetMockState, setMockAdmin } from "@/lib/mock/server";

// Developer toolbar for the mock data (lib/mock). Shown in `npm run dev`, or in
// any build while mock data is on, so a demo never runs on mock data unnoticed.
// Switching mode reloads the page so every screen reads from the new source.

const IS_DEV = process.env.NODE_ENV !== "production";

const noSubscribe = () => () => {};

export function MockToolbar() {
  const on = useMockMode();
  // Read once on the client; changing it reloads the page.
  const admin = useSyncExternalStore(noSubscribe, isMockAdmin, () => true);
  const [open, setOpen] = useState(false);
  const panelId = useId();

  if (!IS_DEV && !on && !MOCK_DEFAULT) return null;

  function toggle() {
    setMockOn(!on);
    window.location.reload();
  }

  function reset() {
    resetMockState();
    window.location.reload();
  }

  return (
    <div className="fixed bottom-4 left-16 z-50 flex flex-col items-start text-small">
      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label="ข้อมูลจำลอง"
          className="mb-2 w-80 rounded-lg border border-border bg-bg p-4 text-text shadow-md"
        >
          <div className="flex items-start justify-between gap-3">
            <p className="font-semibold">ข้อมูลจำลอง (สำหรับพัฒนา)</p>
            <button type="button" onClick={() => setOpen(false)} aria-label="ปิด" className="-m-1 rounded-sm p-1 text-text-muted hover:text-text">
              <X className="size-4" strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
          <p className="mt-1 text-tiny text-text-muted">
            เมื่อเปิด หน้าเว็บจะใช้ข้อมูลตัวอย่างในเบราว์เซอร์แทน API จริง รูปแบบข้อมูลตรงกับ Contract.md
          </p>
          <label className="mt-3 flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-md bg-surface px-3">
            <span>ใช้ข้อมูลจำลอง</span>
            <input type="checkbox" role="switch" checked={on} onChange={toggle} className="size-5 accent-[var(--color-primary)]" />
          </label>
          {on && (
            <>
              <label className="mt-2 flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-md bg-surface px-3">
                <span>บัญชีผู้ดูแล (ADMIN_EMAILS)</span>
                <input
                  type="checkbox"
                  role="switch"
                  checked={admin}
                  onChange={() => {
                    setMockAdmin(!admin);
                    window.location.reload();
                  }}
                  className="size-5 accent-[var(--color-primary)]"
                />
              </label>
              <ul className="mt-3 space-y-1 text-tiny text-text-muted">
                <li>• PDF ใดก็ได้ → CV ตัวอย่าง</li>
                <li>• ชื่อไฟล์มีคำว่า &quot;scan&quot; → อ่านไฟล์ไม่ได้</li>
                <li>• ไฟล์ที่ไม่ใช่ PDF หรือเกิน 5 MB → ข้อผิดพลาดของไฟล์</li>
              </ul>
              <button
                type="button"
                onClick={reset}
                className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md border border-border px-3 hover:bg-surface"
              >
                <RotateCcw className="size-4" strokeWidth={1.75} aria-hidden="true" />
                รีเซ็ตข้อมูลจำลอง
              </button>
            </>
          )}
        </div>
      )}
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex min-h-11 items-center gap-2 rounded-full border px-4 font-medium shadow-md ${
          on ? "border-warning bg-bg text-warning" : "border-border bg-bg text-text-muted"
        }`}
      >
        <FlaskConical className="size-4" strokeWidth={1.75} aria-hidden="true" />
        ข้อมูลจำลอง: {on ? "เปิด" : "ปิด"}
      </button>
    </div>
  );
}
