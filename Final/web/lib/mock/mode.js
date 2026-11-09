"use client";

import { useSyncExternalStore } from "react";

// Mock switch. The default comes from NEXT_PUBLIC_MOCK_API ("1" = on), which is
// read at build time: .env.development turns it on for `npm run dev`, and the
// Docker build leaves it off so the app talks to the real api.
// The choice can be changed in the browser (mock toolbar, or ?mock=on / ?mock=off)
// and is kept in localStorage until it is changed again.

const KEY = "cm-mock";
const EVENT = "cm-mock-change";

export const MOCK_DEFAULT = process.env.NEXT_PUBLIC_MOCK_API === "1";

let queryApplied = false;

/** Apply ?mock=on|off from the URL once per page load, so a link can switch modes. */
export function applyMockQuery() {
  if (queryApplied) return;
  queryApplied = true;
  const value = new URLSearchParams(window.location.search).get("mock");
  if (value === "on" || value === "off") window.localStorage.setItem(KEY, value);
}

export function isMockOn() {
  if (typeof window === "undefined") return MOCK_DEFAULT;
  // Read the URL switch before the first data call, not after the page has loaded.
  applyMockQuery();
  const saved = window.localStorage.getItem(KEY);
  return saved === null ? MOCK_DEFAULT : saved === "on";
}

export function setMockOn(on) {
  window.localStorage.setItem(KEY, on ? "on" : "off");
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(callback) {
  window.addEventListener(EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

/** Current mock mode for components; the server render assumes the default. */
export function useMockMode() {
  return useSyncExternalStore(subscribe, isMockOn, () => MOCK_DEFAULT);
}
