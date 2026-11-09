// Browser-side helper for calling the API through the /api proxy.
// Errors follow Contract.md section 1: Problem-JSON with a stable `code` and a
// Thai `message_th` that can be shown as is.

const FALLBACK_MESSAGE = "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง";

export class ApiError extends Error {
  constructor(status, problem = {}) {
    super(problem.message_th || FALLBACK_MESSAGE);
    this.name = "ApiError";
    this.status = status;
    this.code = problem.code || "HTTP_ERROR";
    this.messageTh = problem.message_th || FALLBACK_MESSAGE;
    this.details = problem.details;
    this.requestId = problem.request_id;
  }
}

/** Quota headers sent with every authenticated response (Contract.md section 1). */
export function readQuota(headers) {
  const requests = headers.get("x-quota-requests-remaining");
  if (requests === null) return null;
  return {
    requestsRemaining: Number(requests),
    tokensRemaining: Number(headers.get("x-quota-tokens-remaining")),
    resetAt: headers.get("x-quota-reset"),
  };
}

/**
 * Call `/api{path}`. `body` may be a plain object (sent as JSON) or FormData (CV upload).
 * Returns `{ data, quota, requestId }`; throws ApiError on a non-2xx response.
 */
export async function api(path, { method = "GET", body, signal, headers = {} } = {}) {
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const init = { method, signal, credentials: "same-origin", headers: { ...headers } };
  if (body !== undefined) {
    init.body = isForm ? body : JSON.stringify(body);
    if (!isForm) init.headers["Content-Type"] = "application/json";
  }

  let res;
  try {
    res = await fetch(`/api${path}`, init);
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError(0, { code: "NETWORK_ERROR", message_th: "เชื่อมต่อไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่" });
  }

  const quota = readQuota(res.headers);
  const requestId = res.headers.get("x-request-id");
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!res.ok) throw new ApiError(res.status, { request_id: requestId, ...(data || {}) });
  return { data, quota, requestId };
}
