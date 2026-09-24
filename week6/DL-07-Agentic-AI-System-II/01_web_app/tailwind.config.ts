import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#071d35",
        cloud: "#f8fbff",
        aqua: "#2785b7",
        pine: "#123f65",
        sand: "#e9f4fa"
      },
      fontFamily: {
        display: ["Georgia", "Times New Roman", "serif"],
        sans: [
          "var(--font-noto-sans-thai)",
          "Noto Sans Thai",
          "var(--font-inter)",
          "Inter",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
        mono: [
          "var(--font-mono)",
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
      },
      boxShadow: { float: "0 22px 60px rgba(7, 29, 53, .16)" }
    }
  },
  plugins: []
} satisfies Config;
