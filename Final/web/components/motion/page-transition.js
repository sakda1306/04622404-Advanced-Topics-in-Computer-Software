"use client";

import { createContext, Suspense, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PAGE_TRANSITION, TRANSITION_PAGES } from "@/lib/motion";
import { LogoMark } from "@/components/logo";
import { DotGrid } from "@/components/motion/dot-grid";
import { DotCurtain } from "@/components/motion/dot-curtain";
import { useReducedMotion } from "@/lib/use-motion";
import { GenerateStage } from "@/components/motion/generate-stage";

// Full-screen page transition (DesignSystem.md 1.3), shown when moving between
// the major pages in TRANSITION_PAGES; other page changes happen normally.
//
// 1. Cover: dots stream in from the left and right edges, row by row, and swell
//    into tiles until the screen is filled (components/motion/dot-curtain.js).
// 2. Hold: once filled, it stays until PAGE_TRANSITION.minHold has passed AND the new page is
//    ready: its route has rendered, and no component on it is still holding the
//    panel through usePageReady(false) (pages that load data do this).
// 3. Reveal: the dots stream back out to the sides and focus moves to the new <h1>.
// After PAGE_TRANSITION.maxHold the panel lifts anyway, so a stuck page shows its
// own loading or error state.
//
// The new page never shows before the screen is filled: a link click (caught in
// the capture phase, so every next/link works without changes) or navigate() from
// code only changes the page once the dots have covered it. Browser back/forward
// has already changed the page, so the page is hidden until the screen is filled.
// Add data-transition="off" to a link to skip the transition.

const TransitionContext = createContext(null);

const now = () => performance.now();

function focusHeading() {
  const heading = document.querySelector("main h1");
  if (!heading) return;
  if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
  heading.focus({ preventScroll: true });
}

const isMajor = (path) => TRANSITION_PAGES.includes(path);
/** Run the transition for this page change? */
const wants = (from, to) => from !== to && isMajor(from) && isMajor(to);

const holdFor = (kind) =>
  kind === "success" ? PAGE_TRANSITION.successHold : kind === "generate" ? PAGE_TRANSITION.generateHold : PAGE_TRANSITION.minHold;

/** The timing rules, outside React so the callbacks can call each other freely. */
function createTransition(setView, initialPath) {
  const r = {
    active: false,
    covered: false,
    onCovered: [],
    startedAt: 0,
    hold: 0,
    navDone: true,
    pending: 0,
    path: initialPath,
    timers: [],
    revealTimer: null,
  };

  const later = (fn, ms) => r.timers.push(setTimeout(fn, ms));
  const clearTimers = () => {
    r.timers.forEach(clearTimeout);
    r.timers = [];
  };

  function finish({ navigated = true } = {}) {
    if (!r.active) return;
    r.active = false;
    r.covered = false;
    r.onCovered = [];
    clearTimers();
    setView((v) => v && { ...v, phase: "reveal" });
    r.revealTimer = setTimeout(() => {
      r.revealTimer = null;
      setView(null);
      // Wait for React to drop `inert` from the page before moving focus into it.
      if (navigated) requestAnimationFrame(() => requestAnimationFrame(focusHeading));
    }, PAGE_TRANSITION.reveal);
  }

  function check() {
    if (!r.active) return;
    const wait = r.startedAt + r.hold - now();
    if (wait > 0) later(check, wait);
    else if (r.navDone && r.pending === 0) finish();
  }

  /** Cover the page. Called again while active, it only updates the content. */
  function begin({ kind = "default", message, detail, stage, hold, hidePage = false } = {}) {
    // The hold counts from the moment the screen is filled, so the page is fully
    // covered for at least that long.
    const minHold = (hold ?? holdFor(kind)) + PAGE_TRANSITION.cover;
    if (r.active) {
      r.hold = Math.max(r.hold, minHold);
      setView((v) => ({ ...v, kind, message, detail, stage: stage ?? v?.stage }));
      return;
    }
    // A new page change during the reveal of the last one: keep this panel.
    clearTimeout(r.revealTimer);
    r.revealTimer = null;
    r.active = true;
    r.covered = false;
    r.onCovered = [];
    r.startedAt = now();
    r.hold = minHold;
    r.navDone = false;
    setView({ phase: "cover", kind, message, detail, stage, hidePage });
    later(() => {
      r.covered = true;
      setView((v) => (v && v.phase === "cover" ? { ...v, phase: "hold" } : v));
      const queued = r.onCovered;
      r.onCovered = [];
      queued.forEach((fn) => fn());
    }, PAGE_TRANSITION.cover);
    later(check, minHold);
    later(() => finish(), PAGE_TRANSITION.maxHold);
  }

  /** Runs fn once the screen is filled (now, if it already is). */
  function whenCovered(fn) {
    if (!r.active || r.covered) fn();
    else r.onCovered.push(fn);
  }

  /** The user tapped through a longer message: fall back to the normal minimum. */
  function skip() {
    const base = PAGE_TRANSITION.minHold + PAGE_TRANSITION.cover;
    if (!r.active || r.hold <= base) return;
    r.hold = base;
    clearTimers();
    later(() => finish(), PAGE_TRANSITION.maxHold - (now() - r.startedAt));
    check();
  }

  /** Keeps the panel up until the returned release() is called. */
  function holdOpen() {
    r.pending += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      r.pending -= 1;
      // Next frame, not now: a remount (Strict Mode, or `ready` flipping back) may
      // take the hold again straight away.
      requestAnimationFrame(check);
    };
  }

  /** The route has rendered. Returns a cleanup. */
  function arrived(path) {
    if (path === r.path) return undefined;
    const first = r.path === null;
    r.path = path;
    if (first) return undefined;
    if (!r.active) return undefined;
    r.navDone = true;
    // Effects of the new page (usePageReady) ran before this one, so its holds are
    // already counted; check on the next frame.
    const frame = requestAnimationFrame(check);
    return () => cancelAnimationFrame(frame);
  }

  return {
    begin,
    whenCovered,
    finish,
    holdOpen,
    skip,
    arrived,
    currentPath: () => r.path,
    dispose() {
      clearTimers();
      clearTimeout(r.revealTimer);
    },
  };
}

/**
 * Reports the current path. usePathname needs a Suspense boundary on dynamic
 * routes (Cache Components), so it lives in its own small component.
 */
function PathWatcher({ transition }) {
  const pathname = usePathname();
  useEffect(() => transition.arrived(pathname), [transition, pathname]);
  return null;
}

export function PageTransitionProvider({ children }) {
  const router = useRouter();
  const [view, setView] = useState(null); // null | { phase, kind, message, detail, stage }
  const [t] = useState(() => createTransition(setView, null));

  /**
   * router.push / replace with the transition between major pages: the page
   * changes only once the screen is filled. Other page changes go straight through,
   * unless a panel is already up (e.g. from show()), which then covers this one.
   */
  const navigate = useCallback(
    (href, { replace = false, ...options } = {}) => {
      const url = new URL(href, window.location.href);
      const go = () => (replace ? router.replace(href) : router.push(href));
      if (wants(window.location.pathname, url.pathname)) t.begin(options);
      t.whenCovered(go);
    },
    [t, router],
  );

  useEffect(() => {
    function onClick(e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const link = e.target instanceof Element ? e.target.closest("a[href]") : null;
      if (!link || link.dataset.transition === "off" || link.hasAttribute("download")) return;
      if (link.target && link.target !== "_self") return;
      const url = new URL(link.href, window.location.href);
      if (url.origin !== window.location.origin || url.pathname.startsWith("/api/")) return;
      if (!wants(window.location.pathname, url.pathname)) return;
      // Take the click from next/link and change page only once the screen is filled.
      e.preventDefault();
      e.stopPropagation();
      t.begin();
      t.whenCovered(() => router.push(url.pathname + url.search + url.hash));
    }
    function onPopState() {
      // The browser has already changed the page: hide it until the screen is filled.
      const path = t.currentPath();
      if (path !== null && wants(path, window.location.pathname)) t.begin({ hidePage: true });
    }
    document.addEventListener("click", onClick, true);
    window.addEventListener("popstate", onPopState);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("popstate", onPopState);
      t.dispose();
    };
  }, [t, router]);

  const api = useMemo(
    () => ({
      navigate,
      show: t.begin,
      /** Change what the panel shows (e.g. the next generate stage) without restarting it. */
      update: (patch) => setView((v) => v && { ...v, ...patch }),
      /** Lift the panel without a page change, e.g. when the action behind show() failed. */
      cancel: () => t.finish({ navigated: false }),
      holdOpen: t.holdOpen,
    }),
    [navigate, t],
  );

  return (
    <TransitionContext.Provider value={api}>
      {/* While the panel is up, the page behind it takes no clicks or keyboard focus. */}
      {/* After back/forward the new page is already there; keep it out of sight until the screen is filled. */}
      <div
        className={view?.hidePage && view.phase === "cover" ? "invisible contents" : "contents"}
        inert={view ? true : undefined}
      >
        {children}
      </div>
      <Suspense fallback={null}>
        <PathWatcher transition={t} />
      </Suspense>
      {view && <TransitionPanel view={view} onSkip={t.skip} />}
    </TransitionContext.Provider>
  );
}

/** { navigate(href, {replace, kind, message, detail}), show(opts), update(patch), cancel() } */
export function usePageTransition() {
  const ctx = useContext(TransitionContext);
  if (!ctx) throw new Error("usePageTransition needs PageTransitionProvider");
  return ctx;
}

/**
 * Keeps the transition panel up while `ready` is false, e.g. while the page's
 * data loads. Pages that never call it count as ready once they render.
 */
export function usePageReady(ready) {
  const ctx = useContext(TransitionContext);
  useEffect(() => {
    if (ready || !ctx) return undefined;
    return ctx.holdOpen();
  }, [ready, ctx]);
}

function SuccessMark() {
  return (
    <svg viewBox="0 0 52 52" className="size-20" aria-hidden="true">
      <circle className="pt-check-ring" cx="26" cy="26" r="23" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <path className="pt-check-mark" d="M15 27 l7.5 7.5 L37.5 19" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TransitionPanel({ view, onSkip }) {
  const { phase, kind, message, detail, stage } = view;
  const skippable = kind === "success";
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!skippable) return undefined;
    window.addEventListener("keydown", onSkip);
    return () => window.removeEventListener("keydown", onSkip);
  }, [skippable, onSkip]);
  const style = { "--pt-cover": `${PAGE_TRANSITION.cover}ms`, "--pt-reveal": `${PAGE_TRANSITION.reveal}ms` };
  return (
    <div
      className={`pt-panel pt-${phase} fixed inset-0 z-[100] flex items-center justify-center overflow-hidden`}
      style={style}
      onClick={skippable ? onSkip : undefined}
    >
      {/* Dots stream in from both sides and fill the screen, then stream back out. */}
      <DotCurtain phase={phase} cover={PAGE_TRANSITION.cover} reveal={PAGE_TRANSITION.reveal} reduced={reduced} />
      {/* While covered: the same colour, with the twinkling dot grid on top. */}
      <div className="pt-fill bg-curtain absolute inset-0" aria-hidden="true">
        <DotGrid even speed={1.6} intensity={0.8} />
      </div>
      <div role="status" aria-live="polite" className="pt-content relative flex flex-col items-center px-6 text-center">
        {kind === "success" && (
          <>
            <span className="text-curtain-accent">
              <SuccessMark />
            </span>
            <p className="mt-5 text-h2 font-bold text-curtain-fg">{message}</p>
            {detail && <p className="mt-1 text-body text-curtain-muted">{detail}</p>}
            <p className="mt-8 text-tiny text-curtain-muted">แตะหรือกดปุ่มใดก็ได้เพื่อไปต่อ</p>
          </>
        )}
        {kind === "generate" && <GenerateStage stage={stage ?? 0} steps={view.steps} />}
        {kind === "default" && (
          <>
            <span className="pt-logo" style={{ "--color-primary": "#9fd9c6", "--color-bg": "#163144" }}>
              <LogoMark className="size-14" />
            </span>
            <span className="mt-4 text-small text-curtain-muted">{message ?? "กำลังโหลด…"}</span>
          </>
        )}
      </div>
    </div>
  );
}
