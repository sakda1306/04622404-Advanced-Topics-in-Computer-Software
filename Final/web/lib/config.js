// Server-side settings. APP_NAME is read when pages are built (pass it as a
// build argument in Docker); API_BASE_URL is read at request time by the proxy.
export const APP_NAME = process.env.APP_NAME || "CareerMirror";

export function apiBaseUrl() {
  return (process.env.API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
}
