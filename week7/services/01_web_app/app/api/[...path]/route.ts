import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

async function proxy(
  request: NextRequest,
  context: { params: { path: string[] } },
) {
  const suppliedId = request.headers.get("x-request-id");
  const requestId =
    suppliedId && /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(suppliedId)
      ? suppliedId
      : crypto.randomUUID();
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  const target = new URL(
    "/api/" + context.params.path.map(encodeURIComponent).join("/"),
    base,
  );
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of ["cookie", "content-type", "x-request-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("X-Request-ID", requestId);

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method)
        ? undefined
        : await request.arrayBuffer(),
      cache: "no-store",
      signal: AbortSignal.timeout(60_000),
    });
    const responseHeaders = new Headers();
    for (const name of [
      "content-type",
      "set-cookie",
      "retry-after",
      "x-request-id",
    ]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    responseHeaders.set("cache-control", "no-store");
    if (!responseHeaders.has("x-request-id"))
      responseHeaders.set("X-Request-ID", requestId);
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const timedOut =
      error instanceof Error &&
      (error.name === "TimeoutError" || error.name === "AbortError");
    const status = timedOut ? 504 : 502;
    const code = timedOut ? "API_TIMEOUT" : "API_UNAVAILABLE";
    const response = NextResponse.json(
      {
        type:
          "https://errors.football-assistant.local/" +
          code.toLowerCase().replaceAll("_", "-"),
        title: timedOut ? "API timed out" : "API unavailable",
        status,
        code,
        service: "web",
        request_id: requestId,
        detail: timedOut
          ? "รอคำตอบนานเกินไป กรุณาลองใหม่"
          : "เชื่อมต่อระบบไม่ได้ชั่วคราว กรุณาลองใหม่",
      },
      {
        status,
        headers: {
          "Content-Type": "application/problem+json",
          "X-Request-ID": requestId,
          "Cache-Control": "no-store",
        },
      },
    );
    if (context.params.path.join("/") === "auth/logout")
      response.cookies.set("access_token", "", {
        expires: new Date(0),
        path: "/",
        httpOnly: true,
        sameSite: "lax",
      });
    return response;
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
