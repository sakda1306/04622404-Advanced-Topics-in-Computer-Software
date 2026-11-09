import { apiBaseUrl } from "@/lib/config";

// Server-side proxy: the browser calls /api/* on the web origin and this route
// forwards to the api container (Contract.md section 1). The httpOnly auth
// cookie stays on the web origin; the browser never calls the api directly.

// Hop-by-hop and length/encoding headers are recomputed on each side.
const SKIP_REQUEST = new Set(["host", "connection", "keep-alive", "transfer-encoding", "content-length", "accept-encoding"]);
const SKIP_RESPONSE = new Set(["connection", "keep-alive", "transfer-encoding", "content-length", "content-encoding", "set-cookie"]);

function unavailable() {
  return Response.json(
    {
      type: "about:blank",
      title: "API unavailable",
      status: 502,
      code: "INTERNAL_ERROR",
      message_th: "ระบบไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง",
    },
    { status: 502, headers: { "content-type": "application/problem+json" } },
  );
}

async function proxy(request, { params }) {
  const { path = [] } = await params;
  const search = new URL(request.url).search;
  const target = `${apiBaseUrl()}/api/${path.map(encodeURIComponent).join("/")}${search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!SKIP_REQUEST.has(key.toLowerCase())) headers.set(key, value);
  });

  const init = { method: request.method, headers, redirect: "manual", cache: "no-store" };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body; // streamed, so CV uploads are not buffered here
    init.duplex = "half";
  }

  let upstream;
  try {
    upstream = await fetch(target, init);
  } catch {
    return unavailable();
  }

  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!SKIP_RESPONSE.has(key.toLowerCase())) out.append(key, value);
  });
  for (const cookie of upstream.headers.getSetCookie()) out.append("set-cookie", cookie);

  return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers: out });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
