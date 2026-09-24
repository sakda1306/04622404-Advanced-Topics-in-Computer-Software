import { NextResponse } from "next/server";

// Container healthcheck target. Kept dependency-free on purpose: it reports that
// this process serves traffic, not that the backend is up (/status does that).
export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({ status: "ok", ts: new Date().toISOString() });
}
