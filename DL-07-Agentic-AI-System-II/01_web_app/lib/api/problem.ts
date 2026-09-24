/**
 * RFC 9457 (application/problem+json) — the error shape the backend returns.
 * Every failed request in this app ends up as an ApiError so the UI has one
 * thing to catch, whether the failure came from the server or from the network.
 */

export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  /** Backend-specific machine code — this is what the UI should branch on. */
  code?: string;
  /** Field-level validation errors, when the backend sends them. */
  errors?: Record<string, string[]>;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: ProblemDetails;

  constructor(status: number, problem: ProblemDetails) {
    super(problem.detail ?? problem.title ?? `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = problem.code ?? inferCode(status);
    this.problem = problem;
  }

  /** The token is missing, expired, or signed by an issuer the API rejects. */
  get isAuthError(): boolean {
    return this.status === 401 || this.status === 403;
  }

  get isRetryable(): boolean {
    return this.status === 408 || this.status === 429 || this.status >= 500;
  }
}

/** Fallback when the backend answers with a bare status and no problem body. */
function inferCode(status: number): string {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422) return "validation_error";
  if (status === 429) return "rate_limited";
  if (status === 0) return "network_error";
  return status >= 500 ? "server_error" : "request_failed";
}

export function isProblemDetails(value: unknown): value is ProblemDetails {
  return typeof value === "object" && value !== null;
}

/**
 * Message to put in front of a user. Keep the backend's `detail` when there is
 * one — it is already localised by Accept-Language — and fall back to a plain
 * sentence that says what to do next, not just what broke.
 */
export function toUserMessage(error: unknown, locale: "th" | "en" = "th"): string {
  if (error instanceof ApiError) {
    if (error.problem.detail) return error.problem.detail;
    if (error.isAuthError) {
      return locale === "th"
        ? "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่"
        : "Your session has expired. Sign in again.";
    }
    if (error.code === "network_error") {
      return locale === "th"
        ? "ติดต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบว่า API ทำงานอยู่ที่พอร์ต 8000"
        : "Cannot reach the server. Check that the API is running on port 8000.";
    }
    return error.message;
  }
  return locale === "th" ? "เกิดข้อผิดพลาดที่ไม่คาดคิด" : "Something went wrong.";
}
