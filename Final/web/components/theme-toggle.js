"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { Check, Monitor, Moon, Sun } from "lucide-react";

const OPTIONS = [
  { value: "light", label: "สว่าง", Icon: Sun },
  { value: "dark", label: "มืด", Icon: Moon },
  { value: "system", label: "ตามระบบ", Icon: Monitor },
];

// true only after hydration, so the icon never mismatches the server render
const subscribe = () => () => {};
function useMounted() {
  return useSyncExternalStore(subscribe, () => true, () => false);
}

// Theme toggle (DesignSystem.md section 3): icon button in the top bar that
// opens a menu with สว่าง / มืด / ตามระบบ. Works before login.
export function ThemeToggle() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const itemRefs = useRef([]);
  const menuId = useId();

  const current = mounted ? theme ?? "system" : "system";
  const ButtonIcon =
    !mounted || current === "system" ? Monitor : resolvedTheme === "dark" ? Moon : Sun;

  useEffect(() => {
    if (!open) return;
    const selected = Math.max(0, OPTIONS.findIndex((o) => o.value === current));
    itemRefs.current[selected]?.focus();

    function onPointerDown(event) {
      if (!wrapRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open, current]);

  function onMenuKeyDown(event) {
    const items = itemRefs.current;
    const index = items.indexOf(document.activeElement);
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      wrapRef.current?.querySelector("button")?.focus();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      items[(index + step + items.length) % items.length]?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  function choose(value) {
    setTheme(value);
    setOpen(false);
    wrapRef.current?.querySelector("button")?.focus();
  }

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        aria-label="เปลี่ยนธีม"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex size-11 items-center justify-center rounded-md text-text-muted transition-colors duration-150 ease-out hover:bg-surface hover:text-text"
      >
        <ButtonIcon className="size-5" strokeWidth={1.5} aria-hidden="true" />
      </button>

      {open && (
        <ul
          id={menuId}
          role="menu"
          aria-label="ธีม"
          onKeyDown={onMenuKeyDown}
          className="absolute right-0 z-50 mt-2 w-44 rounded-lg border border-border bg-bg p-1 shadow-md"
        >
          {OPTIONS.map(({ value, label, Icon }, i) => {
            const selected = current === value;
            return (
              <li key={value} role="none">
                <button
                  ref={(el) => (itemRefs.current[i] = el)}
                  type="button"
                  role="menuitemradio"
                  aria-checked={selected}
                  onClick={() => choose(value)}
                  className="flex min-h-11 w-full items-center gap-3 rounded-md px-3 text-left text-small text-text hover:bg-surface"
                >
                  <Icon className="size-4 text-text-muted" strokeWidth={1.5} aria-hidden="true" />
                  <span className="flex-1">{label}</span>
                  {selected && (
                    <Check className="size-4 text-primary" strokeWidth={2} aria-hidden="true" />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
