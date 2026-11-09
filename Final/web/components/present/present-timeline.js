"use client";

import { useEffect, useRef, useState } from "react";
import { CheckIcon } from "lucide-react";
import { Stepper, StepperIndicator, StepperItem, StepperNav, StepperSeparator, StepperTitle, StepperTrigger } from "@/components/ui/stepper";
import { useReducedMotion } from "@/lib/use-motion";
import { CHAPTERS } from "@/components/present/chapters";

// Fixed vertical timeline on the left of /present. The active step follows the
// chapter section crossing the middle of the screen; clicking a step scrolls to it.
// It fades out over the hero and closing bands, where no chapter is in view.
// Wide screens only: numbers from xl (1280px), numbers and titles from 2xl (1536px),
// where the margin beside the 1120px content is wide enough.
// Keyboard (any width): Left goes to the previous chapter, Right to the next one;
// Up and Down keep their normal scrolling.

/** Scrolls so chapter `step` (1-based) sits under the top bar. */
function scrollToChapter(step, reduced) {
  document.getElementById(`s${step}`)?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
}

/**
 * The chapter at the reading line (45% down the viewport), from the layout itself:
 * 0 above chapter 1 (hero), CHAPTERS.length + 1 below the last chapter (closing).
 */
function chapterAtReadingLine() {
  const line = window.innerHeight * 0.45;
  let n = 0;
  CHAPTERS.forEach((_, i) => {
    const el = document.getElementById(`s${i + 1}`);
    if (el && el.getBoundingClientRect().top <= line) n = i + 1;
  });
  const last = document.getElementById(`s${CHAPTERS.length}`);
  if (n === CHAPTERS.length && last && last.getBoundingClientRect().bottom < line) n += 1;
  return n;
}

/** Typing in a field, or a key with a modifier (Alt+Left is browser Back), is not ours. */
function isForeignKey(e) {
  if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return true;
  const t = e.target;
  return t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
}

export function PresentTimeline() {
  const [active, setActive] = useState(0);
  const reduced = useReducedMotion();

  useEffect(() => {
    const sections = CHAPTERS.map((_, i) => document.getElementById(`s${i + 1}`)).filter(Boolean);
    const inView = new Set();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const n = Number(e.target.id.slice(1));
          if (e.isIntersecting) inView.add(n);
          else inView.delete(n);
        }
        setActive(inView.size ? Math.min(...inView) : 0);
      },
      // A thin band across the middle of the viewport.
      { rootMargin: "-45% 0px -54% 0px" },
    );
    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, []);

  // Target of the last arrow key while its smooth scroll is still running, so
  // pressing Right twice quickly moves two chapters instead of one.
  const pending = useRef(null);

  useEffect(() => {
    const onKeyDown = (e) => {
      if ((e.key !== "ArrowLeft" && e.key !== "ArrowRight") || e.defaultPrevented || isForeignKey(e)) return;
      const from = pending.current && pending.current.until > Date.now() ? pending.current.step : chapterAtReadingLine();
      const to = e.key === "ArrowRight" ? from + 1 : from - 1;
      if (to < 1 || to > CHAPTERS.length) return;
      e.preventDefault();
      pending.current = { step: to, until: Date.now() + 900 };
      scrollToChapter(to, reduced);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [reduced]);

  const goTo = (step) => scrollToChapter(step, reduced);

  const visible = active > 0;

  return (
    <aside
      aria-label="สารบัญการนำเสนอ"
      inert={!visible}
      className={`fixed top-1/2 left-3 z-30 hidden -translate-y-1/2 rounded-2xl border border-border bg-bg/85 p-3 shadow-sm backdrop-blur transition-opacity duration-300 xl:block 2xl:left-4 2xl:max-w-48 ${
        visible ? "opacity-100" : "pointer-events-none opacity-0"
      }`}
    >
      <Stepper value={active || 1} onValueChange={goTo} orientation="vertical" indicators={{ completed: <CheckIcon className="size-3.5" strokeWidth={2.5} aria-hidden="true" /> }}>
        <StepperNav>
          {CHAPTERS.map((title, i) => (
            <StepperItem key={title} step={i + 1} className="relative items-start">
              <StepperTrigger className="items-start gap-2.5 rounded-md pb-6 text-left group-last/step:pb-0" aria-label={`${i + 1}. ${title}`}>
                <StepperIndicator>{i + 1}</StepperIndicator>
                <StepperTitle className="mt-0.5 hidden text-text-muted transition-colors duration-200 hover:text-text data-[state=active]:font-semibold data-[state=active]:text-text 2xl:block">
                  {title}
                </StepperTitle>
              </StepperTrigger>
              {i < CHAPTERS.length - 1 && (
                <StepperSeparator className="absolute top-7 left-3 m-0 -translate-x-1/2 group-data-[orientation=vertical]/stepper-nav:h-[calc(100%-2rem)] group-data-[state=completed]/step:bg-success" />
              )}
            </StepperItem>
          ))}
        </StepperNav>
      </Stepper>
    </aside>
  );
}
