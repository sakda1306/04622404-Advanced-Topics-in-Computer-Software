"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Maximize2, MessageCircle, Minimize2, X } from "lucide-react";
import { WorkStyleAvatar } from "@/components/avatar/work-style-avatar";
import { answeredCount } from "@/lib/avatar";

// Layout for Profile and Role pages: the page content at full width, and the chat
// behind a round button at the bottom right that shows the user's own work-style
// character. The chat grows out of the button: a 400 × 600 popover on larger
// screens (non-modal, so the page stays readable and usable beside it) and a
// full-height sheet on phones (modal: backdrop, focus kept inside, Escape or a
// swipe down closes it). The chat stays mounted once opened, so its history and a
// half-typed message survive closing. Open or closed is remembered per browser.

const OPEN_KEY = "cm-chat-open";
const HINT_KEY = "cm-chat-hint-seen";
const HINT_MS = 6000;
const PHONE = "(max-width: 639px)";

const isPhone = () => window.matchMedia(PHONE).matches;
const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select, [tabindex]:not([tabindex="-1"])';

/** @param {{chat: React.ReactNode | ((p: {onReply: () => void}) => React.ReactNode), avatarSteps?: object, children: React.ReactNode}} props */
export function WithChat({ chat, avatarSteps, children }) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [wide, setWide] = useState(false);
  const [unread, setUnread] = useState(0);
  const [hint, setHint] = useState(false);
  const [hop, setHop] = useState(0);
  const buttonRef = useRef(null);
  const panelRef = useRef(null);
  const drag = useRef(null);

  const show = useCallback(() => {
    setMounted(true);
    setOpen(true);
    setUnread(0);
    setHint(false);
    setHop((n) => n + 1);
    window.localStorage.setItem(OPEN_KEY, "1");
    window.localStorage.setItem(HINT_KEY, "1");
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    setUnread(0);
    window.localStorage.setItem(OPEN_KEY, "0");
    // Next frame: on a phone the button is hidden while the sheet is open.
    requestAnimationFrame(() => buttonRef.current?.focus());
  }, []);

  // Restore the last state on larger screens (a full-screen sheet should not open
  // by itself on a phone); show the hint bubble once for a first-time visitor.
  useEffect(() => {
    const wasOpen = window.localStorage.getItem(OPEN_KEY) === "1" && !isPhone();
    const seen = window.localStorage.getItem(HINT_KEY) === "1";
    const t = setTimeout(() => {
      if (wasOpen) {
        setMounted(true);
        setOpen(true);
      } else if (!seen) {
        setHint(true);
      }
    }, 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!hint) return undefined;
    const t = setTimeout(() => setHint(false), HINT_MS);
    return () => clearTimeout(t);
  }, [hint]);

  // On open: focus the message box. On a phone, keep Tab inside the sheet.
  useEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current;
    const frame = requestAnimationFrame(() => panel?.querySelector("textarea")?.focus({ preventScroll: true }));
    function onKey(e) {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
        return;
      }
      if (e.key !== "Tab" || !isPhone() || !panel) return;
      const items = [...panel.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    panel?.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(frame);
      panel?.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  // Every reply counts; opening and closing reset the count, so only replies that
  // land while the chat is closed show on the button.
  const onReply = useCallback(() => setUnread((n) => n + 1), []);

  // Swipe down on the sheet's handle to close it (phones).
  const onTouchStart = (e) => {
    drag.current = { y: e.touches[0].clientY, dy: 0 };
  };
  const onTouchMove = (e) => {
    if (!drag.current) return;
    drag.current.dy = Math.max(0, e.touches[0].clientY - drag.current.y);
    if (panelRef.current) panelRef.current.style.translate = `0 ${drag.current.dy}px`;
  };
  const onTouchEnd = () => {
    if (panelRef.current) panelRef.current.style.translate = "";
    if (drag.current?.dy > 90) close();
    drag.current = null;
  };

  const hasAvatar = avatarSteps && answeredCount(avatarSteps) > 0;
  const content = typeof chat === "function" ? chat({ onReply }) : chat;

  return (
    <>
      <div className="min-w-0 space-y-6">{children}</div>

      {/* Phone: dim the page behind the sheet; tapping it closes the chat. */}
      <button
        type="button"
        aria-label="ปิดแชท"
        tabIndex={-1}
        onClick={close}
        className={`chat-backdrop fixed inset-0 z-40 bg-black/40 sm:hidden ${open ? "" : "pointer-events-none opacity-0"}`}
      />

      {mounted && (
        <div
          ref={panelRef}
          id="chat-popover"
          role="dialog"
          aria-label="แชทกับ AI"
          data-state={open ? "open" : "closed"}
          data-wide={wide ? "true" : undefined}
          inert={open ? undefined : true}
          className="chat-pop fixed z-50 flex flex-col border border-border bg-glass shadow-xl"
        >
          <div
            className="flex shrink-0 justify-center pt-2 sm:hidden"
            onTouchStart={onTouchStart}
            onTouchMove={onTouchMove}
            onTouchEnd={onTouchEnd}
            aria-hidden="true"
          >
            <span className="h-1.5 w-10 rounded-full bg-border" />
          </div>
          <div className="absolute top-3 right-3 z-10 flex gap-1 sm:top-4">
            <button
              type="button"
              onClick={() => setWide((v) => !v)}
              aria-label={wide ? "ย่อหน้าต่างแชท" : "ขยายหน้าต่างแชท"}
              aria-pressed={wide}
              className="hidden size-9 items-center justify-center rounded-md text-text-muted transition-colors duration-150 hover:bg-bg hover:text-text sm:inline-flex"
            >
              {wide ? <Minimize2 className="size-4" strokeWidth={2} aria-hidden="true" /> : <Maximize2 className="size-4" strokeWidth={2} aria-hidden="true" />}
            </button>
            <button
              type="button"
              onClick={close}
              aria-label="ปิดแชท"
              className="inline-flex size-9 items-center justify-center rounded-md text-text-muted transition-colors duration-150 hover:bg-bg hover:text-text"
            >
              <X className="size-5" strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
          <div className="min-h-0 flex-1 p-5 pt-3 sm:pt-5 [&>section>header]:pr-16 sm:[&>section>header]:pr-20">{content}</div>
        </div>
      )}

      {/* On a phone the open sheet covers the screen and has its own close button. */}
      <div className={`fixed right-4 bottom-4 z-50 flex items-end gap-3 ${open ? "max-sm:hidden" : ""}`}>
        {hint && !open && (
          <p role="status" className="chat-hint mb-3 rounded-xl rounded-br-sm border border-border bg-glass px-3.5 py-2 text-small text-text shadow-md">
            มีคำถามเรื่องโปรไฟล์? ถามฉันได้นะ!
          </p>
        )}
        <button
          ref={buttonRef}
          type="button"
          onClick={open ? close : show}
          aria-expanded={open}
          aria-controls="chat-popover"
          aria-label={open ? "ปิดแชทกับ AI" : unread ? `แชทกับ AI · ข้อความใหม่ ${unread}` : "แชทกับ AI"}
          className="chat-fab group relative inline-flex size-16 items-center justify-center rounded-full bg-surface shadow-lg ring-2 ring-primary transition-transform duration-150 ease-out hover:scale-105 active:scale-95"
        >
          {!open && <span className="chat-fab-pulse absolute inset-0 rounded-full ring-2 ring-primary" aria-hidden="true" />}
          <span key={hop} className={`flex size-full items-center justify-center overflow-hidden rounded-full ${hop ? "chat-fab-hop" : ""}`}>
            {hasAvatar ? (
              <WorkStyleAvatar steps={avatarSteps} size={66} decorative doodle={false} className="mt-2" />
            ) : (
              <MessageCircle className="size-7 text-primary" strokeWidth={2} aria-hidden="true" />
            )}
          </span>
          <span
            className={`absolute -top-1 -left-1 inline-flex size-6 items-center justify-center rounded-full bg-primary text-on-primary shadow-sm transition-transform duration-200 ${open ? "rotate-90" : ""}`}
            aria-hidden="true"
          >
            {open ? <X className="size-3.5" strokeWidth={2.5} /> : <MessageCircle className="size-3.5" strokeWidth={2.5} />}
          </span>
          {unread > 0 && !open && (
            <span className="tabular absolute -top-1 -right-1 inline-flex min-w-5 items-center justify-center rounded-full bg-danger px-1 text-tiny font-bold text-white shadow-sm" aria-hidden="true">
              {unread}
            </span>
          )}
        </button>
      </div>
    </>
  );
}
