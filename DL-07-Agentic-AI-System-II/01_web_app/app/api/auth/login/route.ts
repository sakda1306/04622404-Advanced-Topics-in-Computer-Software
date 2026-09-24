import { NextResponse } from "next/server";

const KEYCLOAK_URLS = [
  process.env.KEYCLOAK_INTERNAL_URL,
  "http://host.docker.internal:8180",
  "http://127.0.0.1:8180",
  "http://localhost:8180",
].filter(Boolean) as string[];

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { username, password, persona } = body;

    const trimmedUser = (username || "").trim();
    const trimmedPass = (password || "").trim();

    // Determine target persona / role
    const isAdmin =
      persona === "admin" ||
      trimmedUser.toLowerCase() === "admin" ||
      trimmedUser.toLowerCase() === "ops-admin";

    const isTraveler =
      persona === "traveler" ||
      trimmedUser.toLowerCase() === "dev-user";

    // Validate credentials if not using persona shortcut
    if (!persona) {
      if (isAdmin) {
        if (trimmedPass !== "admin1234" && trimmedPass !== "ops-admin-dev-secret-change-me") {
          return NextResponse.json(
            { error: "Invalid credentials", message: "Invalid username or password" },
            { status: 401 },
          );
        }
      } else if (isTraveler) {
        if (trimmedPass !== "dev-password-change-me") {
          return NextResponse.json(
            { error: "Invalid credentials", message: "Invalid username or password" },
            { status: 401 },
          );
        }
      } else {
        return NextResponse.json(
          { error: "Invalid credentials", message: "User account not recognized" },
          { status: 401 },
        );
      }
    }

    // Connect to Keycloak to obtain token
    let tokenData: { access_token: string; expires_in: number; token_type: string; scope: string } | null = null;
    let lastError: unknown = null;

    for (const baseUrl of KEYCLOAK_URLS) {
      try {
        const endpoint = `${baseUrl.replace(/\/$/, "")}/realms/travel-safety/protocol/openid-connect/token`;

        let postBody: URLSearchParams;
        if (isAdmin) {
          postBody = new URLSearchParams({
            grant_type: "client_credentials",
            client_id: "ops-admin",
            client_secret: process.env.KEYCLOAK_OPS_SECRET || "ops-admin-dev-secret-change-me",
          });
        } else {
          postBody = new URLSearchParams({
            grant_type: "password",
            client_id: "dev-cli",
            username: "dev-user",
            password: "dev-password-change-me",
          });
        }

        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: postBody.toString(),
          signal: AbortSignal.timeout(3500),
        });

        if (res.ok) {
          tokenData = await res.json();
          break;
        }
        const errText = await res.text();
        lastError = new Error(`Keycloak returned ${res.status}: ${errText}`);
      } catch (err) {
        lastError = err;
      }
    }

    if (!tokenData) {
      return NextResponse.json(
        {
          error: "Authentication service unavailable",
          details: lastError instanceof Error ? lastError.message : String(lastError),
        },
        { status: 502 },
      );
    }

    const scopes = tokenData.scope ? tokenData.scope.split(" ") : [];

    const userProfile = isAdmin
      ? {
          username: "admin",
          name: "Super Admin",
          role: "admin",
          email: "admin@waypoint.local",
          scopes,
        }
      : {
          username: "dev-user",
          name: "Dev Traveler",
          role: "traveler",
          email: "dev-user@example.com",
          scopes,
        };

    return NextResponse.json({
      access_token: tokenData.access_token,
      token_type: tokenData.token_type || "Bearer",
      expires_in: tokenData.expires_in,
      user: userProfile,
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Bad request", details: err instanceof Error ? err.message : String(err) },
      { status: 400 },
    );
  }
}
