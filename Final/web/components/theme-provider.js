"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

// Light / dark / system theme (PRD FR-36 to FR-38, DesignSystem.md 1.4).
// The choice stays in localStorage and is applied before first paint.
export function ThemeProvider({ children }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
