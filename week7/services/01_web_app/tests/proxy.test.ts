// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "../app/api/[...path]/route";
describe("web API proxy", () => {
  it("preserves Contract v1.2 index readiness errors without turning them into empty data", async () => {
    const problem = {
      status: 503,
      code: "INDEX_NOT_READY",
      detail: "Index is loading",
      request_id: "index-starting",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(problem), {
          status: 503,
          headers: {
            "content-type": "application/problem+json",
            "x-request-id": "index-starting",
          },
        }),
      ),
    );
    const response = await POST(
      new NextRequest("http://localhost/api/admin/kb/reindex", {
        method: "POST",
      }),
      { params: { path: ["admin", "kb", "reindex"] } },
    );
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual(problem);
  });
  it("forwards cookies and creates a correlated request ID", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        headers: {
          "content-type": "application/json",
          "set-cookie": "access_token=demo; HttpOnly; Path=/",
        },
      }),
    );
    vi.stubGlobal("fetch", fetcher);
    const response = await POST(
      new NextRequest("http://localhost/api/chat", {
        method: "POST",
        headers: {
          cookie: "access_token=existing",
          "content-type": "application/json",
        },
        body: JSON.stringify({ message: "hello" }),
      }),
      { params: { path: ["chat"] } },
    );
    const options = fetcher.mock.calls[0][1];
    expect(options.headers.get("cookie")).toBe("access_token=existing");
    expect(options.headers.get("x-request-id")).toMatch(/^[a-f0-9-]{36}$/);
    expect(response.headers.get("x-request-id")).toBe(
      options.headers.get("x-request-id"),
    );
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(await response.json()).toEqual({ ok: true });
  });
  it("returns complete Problem JSON when API is down", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("connect failed")),
    );
    const response = await POST(
      new NextRequest("http://localhost/api/chat", { method: "POST" }),
      { params: { path: ["chat"] } },
    );
    expect(response.status).toBe(502);
    expect(response.headers.get("content-type")).toContain(
      "application/problem+json",
    );
    const data = await response.json();
    expect(data).toMatchObject({
      status: 502,
      code: "API_UNAVAILABLE",
      service: "web",
    });
    for (const key of ["type", "title", "detail", "request_id"])
      expect(data[key]).toBeTruthy();
    expect(data.request_id).toBe(response.headers.get("x-request-id"));
  });
  it("distinguishes timeout and clears cookie on unavailable logout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("timeout", "TimeoutError")),
    );
    const response = await POST(
      new NextRequest("http://localhost/api/auth/logout", { method: "POST" }),
      { params: { path: ["auth", "logout"] } },
    );
    expect(response.status).toBe(504);
    expect(response.headers.get("set-cookie")).toContain(
      "Expires=Thu, 01 Jan 1970",
    );
  });
  it("preserves upstream status, problem and retry delay", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: "RATE_LIMITED" }), {
          status: 429,
          headers: {
            "content-type": "application/problem+json",
            "retry-after": "12",
            "x-request-id": "upstream",
          },
        }),
      ),
    );
    const response = await POST(
      new NextRequest("http://localhost/api/chat", { method: "POST" }),
      { params: { path: ["chat"] } },
    );
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("12");
    expect(response.headers.get("x-request-id")).toBe("upstream");
  });
});
