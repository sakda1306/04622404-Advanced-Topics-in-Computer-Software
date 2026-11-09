"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(callback) {
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}

/**
 * true when the user asked for reduced motion (DesignSystem.md 1.3).
 * Charts pass `isAnimationActive={!reduced}`; HTML bars skip their transition.
 */
export function useReducedMotion() {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    // Server render assumes motion is allowed, so it sends the empty starting
    // state and the client animates from it. With reduced motion the client
    // jumps to the final values on its first render, and globals.css removes
    // the transition itself.
    () => false,
  );
}

/** Shared chart animation: one calm grow-in, the same everywhere. */
export const CHART_MOTION = { duration: 800, easing: "ease-out" };

/**
 * Returns false on the first frame, then true, so a CSS transition can run
 * from the empty state to the real value. Stays true when motion is reduced.
 */
export function useEntered() {
  const reduced = useReducedMotion();
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return reduced || entered;
}

/** Counts from 0 to `value` with an ease-out curve; jumps straight to it when motion is reduced. */
export function useCountUp(value, duration = CHART_MOTION.duration) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(0);
  const frame = useRef(0);

  useEffect(() => {
    if (reduced) return undefined;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      setShown(value * eased);
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [value, duration, reduced]);

  return reduced ? value : shown;
}
