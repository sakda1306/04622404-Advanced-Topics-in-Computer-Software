"use client";

import { useEffect, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { ShaderBackground } from "@/components/ui/shader-background";

// Silk background behind every page except the landing page (which has its own
// brighter silk bands). Dimmer and slower than the landing: a fixed layer under
// the page, with a wash on top so it stays in the background. Colours follow the
// theme: deep navy in dark, pale mist in light (dark page text stays readable).
// While it is on, <html> gets `has-silk`, which turns the cards above it into
// frosted, see-through panels (globals.css).

const PALETTES = {
  dark: ["#060d12", "#0e2230", "#2f6f68", "#08141c"],
  light: ["#f3f8f7", "#e2eeea", "#bfe0d6", "#edf4f2"],
};
const SPEED = 0.45; // of the landing silk's pace

const noSubscribe = () => () => {};

export function AppBackground() {
  const pathname = usePathname();
  const { resolvedTheme } = useTheme();
  // The theme is only known in the browser; render nothing on the server.
  const mounted = useSyncExternalStore(noSubscribe, () => true, () => false);
  // The landing page and the presentation page (/present) have their own silk bands.
  const on = pathname !== "/" && pathname !== "/present";

  useEffect(() => {
    document.documentElement.classList.toggle("has-silk", on);
    return () => document.documentElement.classList.remove("has-silk");
  }, [on]);

  if (!on || !mounted) return null;
  const theme = resolvedTheme === "dark" ? "dark" : "light";
  return (
    <div className="pointer-events-none fixed inset-0 -z-10" aria-hidden="true">
      <ShaderBackground colors={PALETTES[theme]} speed={SPEED} grain={theme === "dark" ? 0.16 : 0.08} className="absolute inset-0" />
      <div className={`absolute inset-0 ${theme === "dark" ? "bg-[#050b10]/45" : "bg-white/30"}`} />
    </div>
  );
}
