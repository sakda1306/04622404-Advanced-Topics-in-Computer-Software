"use client";

import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import { BookOpen, ClipboardList, ExternalLink, FileText, MessageCircle, PencilLine } from "lucide-react";

// Evidence citation (DesignSystem.md section 3, FR-16): an inline [n] that opens
// a popover with the evidence label and the excerpt on hover, click or focus +
// Enter. Esc and a click outside close it. Used on the profile and in chat.

const KIND_ICON = { cv_line: FileText, answer: ClipboardList, chat: MessageCircle, rag_chunk: BookOpen, user_action: PencilLine };

export function Citation({ n, label, excerpt, kind, url }) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const wrapRef = useRef(null);
  const buttonRef = useRef(null);
  const hoverTimer = useRef(null);
  const id = useId();
  const Icon = KIND_ICON[kind] ?? BookOpen;

  useEffect(() => {
    if (!open) return;
    function onDown(e) {
      if (!wrapRef.current?.contains(e.target)) {
        setOpen(false);
        setPinned(false);
      }
    }
    function onKey(e) {
      if (e.key === "Escape") {
        setOpen(false);
        setPinned(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const hover = (value) => {
    clearTimeout(hoverTimer.current);
    if (pinned) return;
    hoverTimer.current = setTimeout(() => setOpen(value), value ? 120 : 180);
  };

  return (
    <span ref={wrapRef} className="relative inline-block align-baseline" onMouseEnter={() => hover(true)} onMouseLeave={() => hover(false)}>
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`หลักฐาน ${n}: ${label}`}
        onClick={() => {
          setPinned(!open || !pinned);
          setOpen(!open || !pinned);
        }}
        className="tabular mx-0.5 inline-flex min-h-6 min-w-6 items-center justify-center rounded-sm px-1 font-[family-name:var(--font-latin-first)] text-tiny font-semibold text-accent hover:bg-primary-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        [{n}]
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute top-full left-1/2 z-50 mt-1 block w-64 -translate-x-1/2 rounded-md border border-border bg-surface p-3 text-left whitespace-normal shadow-lg"
        >
          <span className="flex items-center gap-1.5 text-tiny font-semibold text-text">
            <Icon className="size-3.5 shrink-0 text-accent" strokeWidth={2} aria-hidden="true" />
            {label}
          </span>
          {excerpt && <span className="mt-1 block text-tiny leading-relaxed text-text-muted">{excerpt}</span>}
          {url && (
            <a href={url} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-center gap-1 text-tiny font-semibold text-accent hover:underline">
              เปิดแหล่งที่มา
              <ExternalLink className="size-3" strokeWidth={2} aria-hidden="true" />
            </a>
          )}
        </span>
      )}
    </span>
  );
}

/* ---------- profile evidence: one number per evidence id across the page ---------- */

const EvidenceContext = createContext({ evidence: {}, numbers: {} });

/** Numbers evidence in the order the profile lists it, so [1] means the same thing everywhere. */
export function EvidenceProvider({ evidence, children }) {
  const numbers = Object.fromEntries(Object.keys(evidence ?? {}).map((id, i) => [id, i + 1]));
  return <EvidenceContext.Provider value={{ evidence: evidence ?? {}, numbers }}>{children}</EvidenceContext.Provider>;
}

/** Inline citations for a list of evidence ids; unknown ids are skipped. */
export function Cite({ ids }) {
  const { evidence, numbers } = useContext(EvidenceContext);
  const known = [...new Set(ids ?? [])].filter((id) => evidence[id]);
  if (!known.length) return null;
  return (
    <span className="whitespace-nowrap">
      {known.map((id) => (
        <Citation key={id} n={numbers[id]} label={evidence[id].label_th} excerpt={evidence[id].excerpt} kind={evidence[id].kind} />
      ))}
    </span>
  );
}

/* ---------- chat: text with [n] markers and the message's sources ---------- */

/** Renders "… [1] …" with each marker as a Citation from `sources` (ChatResponse.sources). */
export function TextWithCitations({ text, sources = [] }) {
  const byN = Object.fromEntries(sources.map((s) => [s.n, s]));
  const parts = String(text).split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = /^\[(\d+)\]$/.exec(part);
    const source = m && byN[Number(m[1])];
    if (!source) return <span key={i}>{part}</span>;
    return <Citation key={i} n={source.n} label={source.label_th} url={source.url} />;
  });
}
