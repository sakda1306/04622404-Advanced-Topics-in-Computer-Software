# 08 — Frontend (01_web_app)

> Paths are relative to `DL-07-Agentic-AI-System-II/01_web_app/`.

## Stack

Next.js 15.5 App Router, React 19, TypeScript 5.9, Tailwind 3.4, TanStack Query 5, react-hook-form + zod, Leaflet, lucide-react, motion (`package.json`, `package-lock.json`). `output: "standalone"` (`next.config.ts`). `<html lang="th">` (`app/layout.tsx`).

## Routing and pages

| Route | File | Type | Content |
|---|---|---|---|
| `/` | `app/page.tsx` | Server component shell | Marketing sections + `TravelForm`, `RoutePreview`, `RecommendationDashboard` |
| `/status` | `app/status/page.tsx` | `"use client"` | Service status via `useQuery(fetchServiceStatus)` |
| `/admin` | `app/admin/page.tsx` | `"use client"` | Admin dashboard; calls `getAdminJobs` / `getFeedbackReviews`, but the cards and job rows are **hard-coded placeholders** |
| `/api/health` | `app/api/health/route.ts` | Route handler | Container healthcheck, no backend check |

No auth pages, no route protection, no middleware.ts: Not found in code.

## State management

| State | Mechanism | File |
|---|---|---|
| Server data (status, admin) | TanStack Query; `staleTime 30s`; retry only `ApiError.isRetryable` and max 2; mutations no retry | `components/providers.tsx:8-19` |
| Trip flow (status machine `idle → geocoding → submitting → streaming → success/error`, points, recommendation, mock flag, progress message, road route) | React Context + `useState` | `components/trip-context.tsx:39-46`, `116-133` |
| Race protection | `requestSeq` ref; stale responses dropped | `trip-context.tsx:50-51` |
| Form state | react-hook-form + `zodResolver` | `components/travel-form.tsx:8-28` |

## Data fetching

| Pattern | File |
|---|---|
| One fetch wrapper for all backend calls (`apiFetch`) adding auth, locale, idempotency | `lib/api/client.ts:55-107` |
| Typed API object | `lib/api/index.ts` |
| 200 vs 202 handling then SSE follow with ticket, 45 s timeout | `lib/api/index.ts` (`followRecommendationJob`) |
| Tolerant response normaliser for an unstable contract | `lib/api/service-status.ts:42-90` |
| External APIs called directly from the browser: Nominatim (rate-throttled), OSRM | `lib/geocode.ts:55-70`, `lib/routing.ts:20-30` |
| Fallback: on any error show a client-side mock recommendation, flagged `usingMock` | `trip-context.tsx:104-111`, `lib/mock-recommendation.ts` |
| User-facing Thai error text from Problem Details | `lib/api/problem.ts` (`toUserMessage`) |

## File upload UI

Not found in code.

## Component organisation

```text
components/
  providers.tsx                 QueryClient + TripProvider
  trip-context.tsx              flow state + submit()
  travel-form.tsx               zod form
  recommendation-dashboard.tsx  renders RecommendationResponse (240 lines)
  route-preview.tsx             map wrapper
  site-header.tsx
  ui/                           presentational: trip-map (Leaflet), hero, testimonials, reveal
lib/
  api/                          client, problem, service-status, index
  types.ts                      hand-written API types
  geocode.ts, routing.ts        external helpers
  mock-recommendation.ts        offline fallback data
  utils.ts                      clsx helper
```

## Styling

Tailwind utility classes inline; custom palette (`ink`, `cloud`, `aqua`, `pine`, `sand`), display font Georgia, `shadow-float` (`tailwind.config.ts`). Global CSS in `app/globals.css`. Status page pairs icons + words with colour for accessibility (comment in `app/status/page.tsx`). No component library.

## Mapping to CareerMirror

| CareerMirror need | Reuse |
|---|---|
| Chat with completeness meter | Copy `trip-context.tsx` pattern (status machine + seq guard) for chat state; progress via SSE wrapper |
| Questionnaire | `travel-form.tsx` pattern (zod schema with Thai messages + RHF) |
| CV PDF upload | Not present; pass `rawBody: FormData` (already supported by `apiFetch`, `client.ts:49`; JSON `Content-Type` is only set when `body` is used, `client.ts:78`) |
| API client | Copy `lib/api/client.ts` + `problem.ts` as-is; replace token source |
| Fallback UI | Keep "show cached/degraded result + banner" idea; avoid silent mock data in production |
