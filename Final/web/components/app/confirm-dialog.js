"use client";

import { useEffect, useRef } from "react";
import { Button } from "@/components/intake/ui";

// Dialog for destructive actions (DesignSystem.md section 3). A native <dialog>
// opened with showModal() traps focus and closes on Esc; the cancel button gets
// focus first so Enter never confirms by accident.
export function ConfirmDialog({ open, title, children, confirmLabel = "ยืนยัน", cancelLabel = "ยกเลิก", danger = false, loading = false, onConfirm, onCancel }) {
  const ref = useRef(null);
  const cancelRef = useRef(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      cancelRef.current?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!loading) onCancel();
      }}
      onClick={(e) => {
        // a click on the backdrop (the dialog element itself) cancels
        if (e.target === ref.current && !loading) onCancel();
      }}
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-border bg-surface p-0 text-text shadow-xl backdrop:bg-black/40"
    >
      <div className="p-6">
        <h2 id="confirm-title" className="text-h3 font-semibold text-text">
          {title}
        </h2>
        <div className="mt-2 text-small text-text-muted">{children}</div>
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button ref={cancelRef} variant="secondary" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}
