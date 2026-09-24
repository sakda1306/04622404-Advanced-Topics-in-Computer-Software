import { NextResponse } from "next/server";

export async function POST() {
  const candidateUrls = [
    process.env.KEYCLOAK_INTERNAL_URL,
    "http://host.docker.internal:8180",
    "http://127.0.0.1:8180",
    "http://localhost:8180",
  ].filter(Boolean) as string[];

  const clientSecret = process.env.KEYCLOAK_OPS_SECRET || "ops-admin-dev-secret-change-me";

  let lastError: unknown = null;

  for (const base of candidateUrls) {
    try {
      const endpoint = `${base.replace(/\/$/, "")}/realms/travel-safety/protocol/openid-connect/token`;
      const body = new URLSearchParams({
        grant_type: "client_credentials",
        client_id: "ops-admin",
        client_secret: clientSecret,
      });

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
        signal: AbortSignal.timeout(3000),
      });

      if (res.ok) {
        const data = await res.json();
        return NextResponse.json(data);
      }
      const errText = await res.text();
      lastError = new Error(`Keycloak responded with ${res.status}: ${errText}`);
    } catch (err) {
      lastError = err;
    }
  }

  return NextResponse.json(
    {
      error: "Could not connect to Keycloak",
      details: lastError instanceof Error ? lastError.message : String(lastError),
    },
    { status: 502 },
  );
}
