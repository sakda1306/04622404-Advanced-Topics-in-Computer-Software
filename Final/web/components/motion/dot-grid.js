"use client";

import { useEffect, useRef } from "react";
import { DOT_GRID } from "@/lib/motion";
import { useReducedMotion } from "@/lib/use-motion";

// Twinkling dot grid for dark brand areas (landing hero, final call to action,
// page-transition panel). Every dot twinkles on its own: each gets a random
// phase, speed and peak brightness. Dots are strong at the left and right edges
// and fade out towards the middle, where the headline sits, so text contrast is
// set by the gradient alone. Decorative only: aria-hidden, no pointer events.
// The loop pauses off-screen and in hidden tabs; with reduced motion it draws
// one still frame.

const smoothstep = (a, b, x) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};
const between = ([lo, hi]) => lo + Math.random() * (hi - lo);

/** 0 in the middle of the width, 1 at the edges. `clear` widens the empty middle (0..1). */
const edgeWeight = (fx, clear) => smoothstep(clear * 0.5, 0.98, Math.abs(fx - 0.5) * 2);

/** Vertical falloff: "top" keeps dots on the upper (deep) end of the gradient. */
const VERTICAL = {
  none: () => 1,
  top: (fy) => 1 - smoothstep(0.3, 0.85, fy),
};

function buildDots(width, height, { spacing, clear, vertical, even }) {
  const dots = [];
  const cols = Math.ceil(width / spacing);
  const rows = Math.ceil(height / spacing);
  const fall = VERTICAL[vertical] ?? VERTICAL.none;
  for (let row = 0; row <= rows; row += 1) {
    for (let col = 0; col <= cols; col += 1) {
      const x = col * spacing;
      const y = row * spacing;
      const weight = (even ? 0.75 : edgeWeight(x / width, clear)) * fall(y / height);
      // Thin the grid where the weight is low, like the reference: sparse in the
      // middle, dense at the edges.
      if (weight < 0.04 || Math.random() > weight * 1.15) continue;
      const sparkle = Math.random() < DOT_GRID.sparkle;
      dots.push({
        x,
        y,
        r: between(DOT_GRID.radius),
        phase: Math.random() * Math.PI * 2,
        speed: (Math.PI * 2) / between(DOT_GRID.cycle),
        peak: weight * (sparkle ? 1 : 0.5 + Math.random() * 0.2),
      });
    }
  }
  return dots;
}

/**
 * @param {object} props
 * @param {number} [props.intensity] peak opacity of the brightest dot (0..1)
 * @param {number} [props.speed] twinkle speed multiplier
 * @param {number} [props.clear] how wide the empty middle is (0 = none, 1 = only the very edges)
 * @param {"none"|"top"} [props.vertical] vertical falloff
 * @param {boolean} [props.even] spread dots evenly instead of fading towards the middle
 */
export function DotGrid({ intensity = 0.7, speed = 1, clear = 0.35, vertical = "none", even = false, className = "" }) {
  const canvasRef = useRef(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!ctx) return undefined;

    let dots = [];
    let width = 0;
    let height = 0;
    let colour = getComputedStyle(canvas).color;
    let frame = 0;
    let last = 0;
    let visible = true;
    const start = performance.now() - Math.random() * 10000;

    function draw(now) {
      const t = (now - start) / 1000;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = colour;
      for (const d of dots) {
        const wave = 0.5 + 0.5 * Math.sin(t * d.speed * speed + d.phase);
        // Squared, so each dot spends most of its cycle dim and flashes briefly.
        const alpha = d.peak * intensity * wave * wave;
        if (alpha < 0.03) continue;
        ctx.globalAlpha = alpha;
        ctx.fillRect(d.x - d.r, d.y - d.r, d.r * 2, d.r * 2);
      }
      ctx.globalAlpha = 1;
    }

    function loop(now) {
      frame = requestAnimationFrame(loop);
      if (now - last < 1000 / DOT_GRID.fps) return;
      last = now;
      draw(now);
    }

    function play() {
      cancelAnimationFrame(frame);
      if (reduced || !visible || document.hidden) {
        draw(start + 2500);
        return;
      }
      frame = requestAnimationFrame(loop);
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      dots = buildDots(width, height, { spacing: DOT_GRID.spacing, clear, vertical, even });
      play();
    }

    const sizeObserver = new ResizeObserver(resize);
    sizeObserver.observe(canvas);
    const viewObserver = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      play();
    });
    viewObserver.observe(canvas);
    // The colour comes from CSS (--dot-color), so re-read it when the theme changes.
    const themeObserver = new MutationObserver(() => {
      colour = getComputedStyle(canvas).color;
      if (reduced) play();
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    document.addEventListener("visibilitychange", play);
    resize();

    return () => {
      cancelAnimationFrame(frame);
      sizeObserver.disconnect();
      viewObserver.disconnect();
      themeObserver.disconnect();
      document.removeEventListener("visibilitychange", play);
    };
  }, [reduced, intensity, speed, clear, vertical, even]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 size-full ${className}`}
      style={{ color: "var(--dot-color)" }}
    />
  );
}
