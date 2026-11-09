"use client";

import { useEffect, useId, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { Info, X } from "lucide-react";

// Click-to-explain for the presentation page (/present). Any block wrapped in
// <Explain tip="..."> opens a longer Thai explanation next to the click point when
// clicked (or with Enter or Space when focused); a second click on the same block,
// a click outside the card, Esc or scrolling closes it. Only the innermost clicked
// block opens its card, so a tile and the items inside it can each have their own.
// Hovering only lifts the block (globals.css, [data-explain]) to show it is clickable.
// One <ExplainLayer /> per page draws the card into document.body, so overflow
// and stacking inside the page never clip it.

const TIP_ID = "present-explain-tip";

let state = { id: null, tip: null, title: null, x: 0, top: 0, bottom: 0 };
const listeners = new Set();

function setState(next) {
  state = next;
  listeners.forEach((l) => l());
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function close() {
  if (state.id) setState({ ...state, id: null });
}

/** Wraps a block so clicking it shows `tip` (a string or a list of paragraphs). */
export function Explain({ as: Tag = "div", tip, title, className = "", children, ...rest }) {
  const id = useId();
  const active = useSyncExternalStore(
    subscribe,
    () => state.id === id,
    () => false,
  );

  if (!tip) return <Tag className={className} {...rest}>{children}</Tag>;

  const toggle = (x, top, bottom) => {
    if (state.id === id) close();
    else setState({ id, tip, title, x, top, bottom });
  };

  return (
    <Tag
      {...rest}
      data-explain=""
      data-explain-active={active || undefined}
      role="button"
      tabIndex={0}
      aria-expanded={active}
      aria-controls={active ? TIP_ID : undefined}
      className={className}
      onClick={(e) => {
        // Links, buttons and form controls inside the block (the interactive demos) keep
        // their own click, and so does selecting text.
        if (e.target instanceof Element && e.target.closest("a, button, input, select, textarea, label")) return;
        if (window.getSelection()?.toString()) return;
        e.stopPropagation(); // the innermost block only
        toggle(e.clientX, e.clientY, e.clientY);
      }}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget || (e.key !== "Enter" && e.key !== " ")) return;
        e.preventDefault();
        const r = e.currentTarget.getBoundingClientRect();
        toggle(r.left + Math.min(r.width / 2, 160), r.top, r.bottom);
      }}
    >
      {children}
    </Tag>
  );
}

const GAP = 16;
const MARGIN = 12;

/** Draws the card of the block that was clicked. Mount once on the page. */
export function ExplainLayer() {
  const s = useSyncExternalStore(
    subscribe,
    () => state,
    () => null,
  );

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") close();
    };
    // The card is placed in screen coordinates, so it would drift from its block.
    const onMove = () => close();
    // React listens on document itself here (the App Router root), so stopPropagation in
    // a block cannot keep its click from this listener: skip clicks on blocks and the card.
    const onClick = (e) => {
      if (!(e.target instanceof Element) || !e.target.closest(`[data-explain], #${TIP_ID}`)) close();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onMove, { passive: true });
    window.addEventListener("resize", onMove);
    document.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onMove);
      window.removeEventListener("resize", onMove);
      document.removeEventListener("click", onClick);
    };
  }, []);

  if (!s?.id) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = Math.min(520, vw - MARGIN * 2);
  let left = s.x + GAP;
  if (left + width > vw - MARGIN) left = s.x - GAP - width;
  left = Math.max(MARGIN, Math.min(left, vw - MARGIN - width));
  // Below the click in the upper half of the screen, above it in the lower half.
  const below = s.bottom < vh * 0.5;
  const pos = below ? { top: s.bottom + GAP } : { bottom: vh - s.top + GAP };
  const paragraphs = Array.isArray(s.tip) ? s.tip : [s.tip];

  return createPortal(
    <div
      id={TIP_ID}
      role="dialog"
      aria-label={s.title || "คำอธิบาย"}
      className="present-type explain-card fixed z-[60] max-h-[70vh] overflow-y-auto rounded-xl border border-border bg-surface p-5 text-left shadow-xl"
      style={{ left, width, ...pos }}
    >
      <button
        type="button"
        onClick={close}
        aria-label="ปิดคำอธิบาย"
        className="absolute top-3 right-3 inline-flex size-8 items-center justify-center rounded-full text-text-muted transition-colors duration-150 hover:bg-bg hover:text-text"
      >
        <X className="size-4" strokeWidth={2} aria-hidden="true" />
      </button>
      {s.title && (
        <p className="mb-2 flex items-start gap-2 pr-8 text-body font-semibold text-text">
          <Info className="mt-1.5 size-5 shrink-0 text-accent" strokeWidth={2} aria-hidden="true" />
          {s.title}
        </p>
      )}
      <div className="space-y-2">
        {paragraphs.map((p) => (
          <p key={p} className="text-small text-text-muted">
            {p}
          </p>
        ))}
      </div>
    </div>,
    document.body,
  );
}
