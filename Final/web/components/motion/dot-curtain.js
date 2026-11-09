"use client";

import { useEffect, useRef } from "react";
import { DOT_CURTAIN } from "@/lib/motion";

// The page-transition cover, drawn on a canvas: dots stream in from the left and
// right edges, row by row at different paces, and swell into tiles until the
// screen is filled with the curtain colour. Opening plays the same timeline
// backwards: tiles shrink back into dots that stream out to the sides.
// With reduced motion the filled curtain just fades in and out.

// The curtain's vertical gradient (same stops as the bg-curtain utility), so the
// filled canvas matches the panel shown while the page is covered.
const STOPS = [
  [0, [12, 25, 34]],
  [0.55, [22, 49, 68]],
  [1, [27, 64, 91]],
];

function colourAt(f) {
  for (let i = 1; i < STOPS.length; i += 1) {
    const [p1, c1] = STOPS[i];
    const [p0, c0] = STOPS[i - 1];
    if (f <= p1) {
      const k = (f - p0) / (p1 - p0);
      return `rgb(${c0.map((v, j) => Math.round(v + (c1[j] - v) * k)).join(" ")})`;
    }
  }
  return `rgb(${STOPS.at(-1)[1].join(" ")})`;
}

const easeOut = (x) => 1 - (1 - x) ** 3;
const clamp01 = (x) => Math.min(1, Math.max(0, x));

/** Per-row timing: a start delay and a travel time, both fractions of the whole run. */
function rowPlan(rows) {
  const plan = [];
  let delay = Math.random() * DOT_CURTAIN.maxDelay;
  for (let r = 0; r < rows; r += 1) {
    // Smoothed noise, so neighbouring rows move in loose bands like streaks.
    delay = 0.55 * (Math.random() * DOT_CURTAIN.maxDelay) + 0.45 * delay;
    const travel = DOT_CURTAIN.travel[0] + Math.random() * (DOT_CURTAIN.travel[1] - DOT_CURTAIN.travel[0]);
    plan.push({ delay, travel: Math.min(travel, 1 - DOT_CURTAIN.grow - delay) });
  }
  return plan;
}

/**
 * @param {{phase: "cover"|"hold"|"reveal", cover: number, reveal: number, reduced: boolean}} props
 */
export function DotCurtain({ phase, cover, reveal, reduced }) {
  const canvasRef = useRef(null);
  const layout = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!ctx) return undefined;

    // Built once per panel, so the reveal retraces the cover's own rows.
    if (!layout.current) {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const size = width < 640 ? DOT_CURTAIN.cellSmall : DOT_CURTAIN.cell;
      const cols = Math.ceil(width / size);
      const rows = Math.ceil(height / size);
      layout.current = {
        width,
        height,
        size,
        cols,
        rows,
        half: Math.ceil(cols / 2),
        left: rowPlan(rows),
        right: rowPlan(rows),
        colours: Array.from({ length: rows }, (_, r) => colourAt((r * size) / height)),
      };
    }
    const L = layout.current;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(L.width * dpr);
    canvas.height = Math.round(L.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    /** progress 0 = empty, 1 = filled. */
    function draw(progress) {
      ctx.clearRect(0, 0, L.width, L.height);
      if (reduced) {
        ctx.globalAlpha = progress;
        for (let r = 0; r < L.rows; r += 1) {
          ctx.fillStyle = L.colours[r];
          ctx.fillRect(0, r * L.size, L.width, L.size + 1);
        }
        ctx.globalAlpha = 1;
        return;
      }
      const { size, grow, lead } = { size: L.size, grow: DOT_CURTAIN.grow, lead: DOT_CURTAIN.lead };
      for (let r = 0; r < L.rows; r += 1) {
        ctx.fillStyle = L.colours[r];
        const y = r * size + size / 2;
        for (let c = 0; c < L.cols; c += 1) {
          const fromLeft = c < L.half;
          const plan = fromLeft ? L.left[r] : L.right[r];
          // Distance from the cell's own edge, 0 at the edge, 1 at the middle.
          const reach = fromLeft ? c / L.half : (L.cols - 1 - c) / (L.cols - L.half);
          const arrive = plan.delay + plan.travel * reach;
          const t = progress - arrive;
          if (t < -lead) continue;
          const x = c * size + size / 2;
          if (t < 0) {
            // Scouts: small dim dots running ahead of the front.
            ctx.globalAlpha = 0.25 + 0.5 * (1 + t / lead);
            const d = 2;
            ctx.fillRect(x - d / 2, y - d / 2, d, d);
            continue;
          }
          const s = easeOut(clamp01(t / grow));
          const d = 2 + (size + 1 - 2) * s;
          ctx.globalAlpha = 0.75 + 0.25 * s;
          ctx.fillRect(x - d / 2, y - d / 2, d, d);
        }
      }
      ctx.globalAlpha = 1;
    }

    if (phase === "hold") {
      draw(1);
      return undefined;
    }
    const duration = phase === "cover" ? cover : reveal;
    const start = performance.now();
    let frame = 0;
    function tick(now) {
      const k = clamp01((now - start) / duration);
      draw(phase === "cover" ? k : 1 - k);
      if (k < 1) frame = requestAnimationFrame(tick);
    }
    draw(phase === "cover" ? 0 : 1);
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [phase, cover, reveal, reduced]);

  return <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none absolute inset-0 size-full" />;
}
