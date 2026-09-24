import { apiFetch } from "./client";

export type ComponentState = "operational" | "degraded" | "down" | "unknown";

export interface ServiceComponent {
  key: string;
  label: string;
  state: ComponentState;
  message?: string;
  checkedAt?: string;
}

export interface ServiceStatus {
  overall: ComponentState;
  components: ServiceComponent[];
  /** Kept so the page can show the untouched payload while the shape settles. */
  raw: unknown;
}

const LABELS: Record<string, string> = {
  api: "ระบบหลัก (API)",
  agent: "ผู้ช่วย AI",
  travel_agent: "ผู้ช่วย AI",
  weather: "ข้อมูลสภาพอากาศ",
  transport: "ข้อมูลการจราจร",
  traffic: "ข้อมูลการจราจร",
  disaster: "ข้อมูลภัยพิบัติ",
  risk_model: "แบบจำลองความเสี่ยง",
  decision_engine: "แบบจำลองความเสี่ยง",
};

export async function fetchServiceStatus(signal?: AbortSignal): Promise<ServiceStatus> {
  const raw = await apiFetch<unknown>("/v1/service-status", { signal });
  return normalize(raw);
}

/**
 * The backend may report components as an array or as a keyed object, so both
 * are accepted. Anything unrecognised still renders, marked as unknown, rather
 * than crashing the page.
 */
export function normalize(raw: unknown): ServiceStatus {
  const root = asRecord(raw);
  const source = root.components ?? root.services ?? root.dependencies ?? root;

  let components: ServiceComponent[] = [];
  if (Array.isArray(source)) {
    components = source.map((entry, index) => {
      const item = asRecord(entry);
      const key = String(item.name ?? item.component ?? item.key ?? index);
      return toComponent(key, item);
    });
  } else {
    components = Object.entries(asRecord(source))
      .filter(([, value]) => typeof value === "object" || typeof value === "string")
      .map(([key, value]) => toComponent(key, value));
  }

  return {
    overall: toState(root.status ?? root.overall ?? root.overall_status) ?? worstOf(components),
    components,
    raw,
  };
}

function toComponent(key: string, value: unknown): ServiceComponent {
  const item = typeof value === "string" ? { status: value } : asRecord(value);
  return {
    key,
    label: LABELS[key] ?? key.replace(/[_-]/g, " "),
    state: toState(item.status ?? item.state) ?? "unknown",
    message: typeof item.message === "string" ? item.message : undefined,
    checkedAt:
      typeof item.checked_at === "string"
        ? item.checked_at
        : typeof item.updated_at === "string"
          ? item.updated_at
          : undefined,
  };
}

function toState(value: unknown): ComponentState | null {
  if (typeof value === "boolean") return value ? "operational" : "down";
  if (typeof value !== "string") return null;
  const v = value.toLowerCase();
  if (["ok", "up", "healthy", "operational", "available"].includes(v)) return "operational";
  if (["degraded", "partial", "slow", "stale"].includes(v)) return "degraded";
  if (["down", "unhealthy", "error", "unavailable", "failed"].includes(v)) return "down";
  return null;
}

function worstOf(components: ServiceComponent[]): ComponentState {
  if (components.some((c) => c.state === "down")) return "down";
  if (components.some((c) => c.state === "degraded")) return "degraded";
  if (components.length > 0 && components.every((c) => c.state === "operational")) {
    return "operational";
  }
  return "unknown";
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
