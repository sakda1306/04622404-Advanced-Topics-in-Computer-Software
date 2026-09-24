import { ApiError, isProblemDetails, type ProblemDetails } from "./problem";

export const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const LOCALE = process.env.NEXT_PUBLIC_DEFAULT_LOCALE ?? "th";

/**
 * Single place the access token comes from.
 *
 * Today: a token pasted into .env.local or sessionStorage.
 * Later: swap the body for the Keycloak session — nothing else in the app
 * needs to change, because every request goes through apiFetch below.
 */
export function getAccessToken(): string | null {
  if (typeof window !== "undefined") {
    // Prioritize admin token when in the admin section
    if (window.location.pathname.startsWith("/admin")) {
      const adminStored =
        window.sessionStorage.getItem("admin_access_token") ??
        window.localStorage.getItem("admin_access_token");
      if (adminStored) return adminStored;
    }

    try {
      const urlParams = new URLSearchParams(window.location.search);
      const queryToken = urlParams.get("token") || urlParams.get("access_token");
      if (queryToken) {
        window.sessionStorage.setItem("access_token", queryToken);
        window.localStorage.setItem("access_token", queryToken);
        return queryToken;
      }
    } catch {
      // Ignore URL parsing errors in non-browser/restricted contexts
    }

    const stored =
      window.sessionStorage.getItem("access_token") ??
      window.localStorage.getItem("access_token");
    if (stored) return stored;
  }
  return process.env.NEXT_PUBLIC_DEV_TOKEN ?? null;
}

/**
 * UUIDv7 — time-ordered, which is what the backend wants for Idempotency-Key.
 * Layout: 48 bits of Unix ms, 4-bit version, 12 random, 2-bit variant, 62 random.
 */
export function uuidv7(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);

  const ms = BigInt(Date.now());
  for (let i = 0; i < 6; i++) {
    bytes[i] = Number((ms >> BigInt(8 * (5 - i))) & 0xffn);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x70; // version 7
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // RFC 4122 variant

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join("-");
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  /** Plain object — serialised as JSON. Pass a string/FormData via `rawBody`. */
  body?: unknown;
  rawBody?: BodyInit;
  /** Reuse a key to retry the same POST safely. Generated per call otherwise. */
  idempotencyKey?: string;
  searchParams?: Record<string, string | number | boolean | undefined | null>;
}

export async function apiFetch<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { body, rawBody, idempotencyKey, searchParams, headers, ...init } = options;
  const method = (init.method ?? (body || rawBody ? "POST" : "GET")).toUpperCase();

  const url = new URL(path.startsWith("http") ? path : `${BASE_URL}${path}`);
  for (const [key, value] of Object.entries(searchParams ?? {})) {
    if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
  }

  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "application/json, application/problem+json");
  finalHeaders.set("Accept-Language", LOCALE);

  const token = getAccessToken();
  if (token) finalHeaders.set("Authorization", `Bearer ${token}`);

  // Every POST needs one; other methods must not send it.
  if (method === "POST") {
    finalHeaders.set("Idempotency-Key", idempotencyKey ?? uuidv7());
  }
  if (body !== undefined && !finalHeaders.has("Content-Type")) {
    finalHeaders.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      method,
      headers: finalHeaders,
      body: rawBody ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch (cause) {
    // fetch only rejects on network/CORS failure — there is no status to read.
    throw new ApiError(0, {
      code: "network_error",
      title: "Cannot reach the API",
      detail: cause instanceof Error ? cause.message : undefined,
    });
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readProblem(response));
  }

  if (response.status === 204 || response.headers.get("Content-Length") === "0") {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function readProblem(response: Response): Promise<ProblemDetails> {
  try {
    const payload: unknown = await response.json();
    if (isProblemDetails(payload)) return { status: response.status, ...payload };
  } catch {
    // Not JSON — a proxy error page or an empty body.
  }
  return { status: response.status, title: response.statusText };
}
