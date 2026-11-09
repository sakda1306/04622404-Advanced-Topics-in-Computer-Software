"use client";

import { Children } from "react";

// Marquee (from the 21st.dev "3D testimonials" component, ported to JavaScript):
// repeats its children `repeat` times in a row (or column) that scrolls forever.
// Each copy slides by its own size plus the gap, so the loop has no jump.
// Speed and spacing come from CSS variables on the element: --duration (one
// loop) and --gap. With prefers-reduced-motion the global rule stops it.
// A decorative marquee (aria-hidden) is not focusable; give screen readers the
// same content another way.

/**
 * @param {object} props
 * @param {boolean} [props.reverse] scroll the other way
 * @param {boolean} [props.pauseOnHover]
 * @param {boolean} [props.vertical] scroll up/down instead of left/right
 * @param {number} [props.repeat] copies of the children (enough to fill the view twice)
 * @param {string} [props.ariaLabel]
 */
export function Marquee({
  className = "",
  reverse = false,
  pauseOnHover = false,
  children,
  vertical = false,
  repeat = 4,
  ariaLabel,
  ...props
}) {
  const hidden = props["aria-hidden"] === true || props["aria-hidden"] === "true";
  const items = Children.toArray(children);
  const copies = Array.from({ length: repeat }, (_, i) => (
    <div
      key={i}
      aria-hidden={i > 0 ? true : undefined}
      className={[
        "flex shrink-0 justify-around [gap:var(--gap)]",
        vertical ? "animate-marquee-vertical flex-col" : "animate-marquee flex-row",
        pauseOnHover ? "group-hover:[animation-play-state:paused]" : "",
        reverse ? "[animation-direction:reverse]" : "",
      ].join(" ")}
    >
      {items}
    </div>
  ));

  return (
    <div
      {...props}
      data-slot="marquee"
      className={`group flex overflow-hidden p-2 [--duration:40s] [--gap:1rem] [gap:var(--gap)] ${vertical ? "flex-col" : "flex-row"} ${className}`}
      aria-label={hidden ? undefined : ariaLabel}
      role={hidden ? undefined : "marquee"}
      tabIndex={hidden ? undefined : 0}
    >
      {copies}
    </div>
  );
}
