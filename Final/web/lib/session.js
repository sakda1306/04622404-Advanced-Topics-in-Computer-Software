"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { data } from "@/lib/data";

// Shared session state for the logged-in pages: the user and today's quota.
// Loaded once and shared by the top bar and the pages, so /api/auth/me is not
// called twice. A 401 sends the user to /login?next=<current path>, except on
// public pages (landing, login, register), which only peek: they ask with
// { redirect: false } to choose between sign-in buttons and "continue" buttons.

let state = { status: "idle", user: null, quota: null };
const listeners = new Set();

function setState(patch) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

function redirectToLogin() {
  const next = window.location.pathname + window.location.search;
  window.location.replace(`/login?next=${encodeURIComponent(next)}`);
}

export async function loadSession({ redirect = true } = {}) {
  // A public page already found no session: a protected page still sends the user to log in.
  if (state.status === "anonymous") {
    if (redirect) redirectToLogin();
    return;
  }
  // After an error the page offers a retry (a reload), so other components do not call again.
  if (state.status !== "idle") return;
  setState({ status: "loading" });
  try {
    const { user } = await data.me();
    setState({ status: "ready", user });
    refreshQuota();
  } catch (error) {
    if (error?.status === 401) {
      setState({ status: "anonymous" });
      if (redirect) redirectToLogin();
    } else {
      setState({ status: "error", error });
    }
  }
}

/** Re-read the quota, e.g. after an action that counts toward it. */
export async function refreshQuota() {
  try {
    setState({ quota: await data.quota() });
  } catch {
    // The quota indicator is P1 (FR-25): if it fails, the bar just hides it.
  }
}

export async function logout() {
  try {
    await data.logout();
  } finally {
    setState({ status: "idle", user: null, quota: null });
    window.location.replace("/login"); // full reload clears every cached page state
  }
}

const subscribe = (l) => {
  listeners.add(l);
  return () => listeners.delete(l);
};
const SERVER_STATE = { status: "idle", user: null, quota: null };

/** Forget the session state so the next page reads it again (after login or register). */
export function resetSession() {
  setState({ status: "idle", user: null, quota: null });
}

/**
 * { status: idle | loading | ready | anonymous | error, user, quota }
 * `redirect: false` only checks: a signed-out visitor stays on the page.
 */
export function useSession({ load = true, redirect = true } = {}) {
  const snapshot = useSyncExternalStore(subscribe, () => state, () => SERVER_STATE);
  useEffect(() => {
    if (load) loadSession({ redirect });
  }, [load, redirect]);
  return snapshot;
}

/**
 * Whether the signed-in user has a profile yet: null while unknown. Pass enabled
 * once signed in; a new `refreshKey` (e.g. the path) asks again.
 */
export function useHasProfile(enabled, refreshKey) {
  const [has, setHas] = useState(null);
  useEffect(() => {
    if (!enabled) return undefined;
    let live = true;
    data.getProfile().then(
      (r) => live && setHas(Boolean(r.profile)),
      () => live && setHas(false),
    );
    return () => {
      live = false;
    };
  }, [enabled, refreshKey]);
  return enabled ? has : null;
}
