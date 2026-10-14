export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
    public retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
let epoch = 0;
export function accountEpoch() {
  return epoch;
}
export function invalidateAccount() {
  epoch += 1;
}
export function isCancelled(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const startedEpoch = epoch;
  const headers = new Headers(init.headers);
  headers.set("X-Request-ID", crypto.randomUUID());
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch("/api" + path, {
    ...init,
    headers,
    cache: "no-store",
    credentials: "same-origin",
  });
  const data = await response.json().catch(() => null);
  if (startedEpoch !== epoch)
    throw new DOMException("บัญชีเปลี่ยนแล้ว", "AbortError");
  if (!response.ok) {
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      path !== "/auth/register" &&
      path !== "/auth/me"
    )
      window.dispatchEvent(new Event("pitchside:expired"));
    throw new ApiError(
      response.status,
      data?.code ?? "REQUEST_FAILED",
      data?.detail ?? "ไม่สามารถโหลดข้อมูลได้ กรุณาลองใหม่",
      data?.request_id ?? response.headers.get("X-Request-ID") ?? undefined,
      Number(response.headers.get("Retry-After")) || undefined,
    );
  }
  return data as T;
}
export function body(value: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(value) };
}
export async function submitFeedback(
  messageId: string,
  rating: number,
  comment?: string,
) {
  const send = () =>
    api<{ ok: boolean }>(
      "/feedback",
      body({ message_id: messageId, rating, comment }),
    );
  try {
    return await send();
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status === 409 &&
      error.code === "MESSAGE_NOT_READY"
    )
      return send();
    throw error;
  }
}
