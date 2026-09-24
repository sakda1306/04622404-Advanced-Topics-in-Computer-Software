# WayPoint — Travel Safety Presentation Layer

Premium, responsive Next.js UI for a travel-safety recommendation platform. It contains a long-scrolling user experience at `/` and an admin UI shell at `/admin`.

## Start

1. Copy `.env.example` to `.env.local` and set the FastAPI base URL.
2. `npm install`
3. `npm run dev`

## API boundary

`lib/types.ts` owns the frontend `TravelRequest` and response display types. `lib/api.ts` owns every HTTP call. The client submits `POST /v1/travel/recommendations`; it does **not** calculate risk. For async results, obtain `POST /v1/jobs/:job_id/stream-ticket`, then open `GET /v1/jobs/:job_id/events?ticket=...`; close `EventSource` on `completed` or `failed`, then fetch `GET /v1/travel/recommendations/:id`.

Implemented API-ready surfaces: recommendation create/read, service status, admin job list, and feedback review list. The dashboard uses polished illustrative states until an API ID is in route state.

## Structure

- `app/page.tsx` — editorial landing page, map presentation shell, recommendation dashboard, FAQ and footer
- `app/admin/page.tsx` — admin overview UI shell
- `components/travel-form.tsx` — React Hook Form + Zod validation and TanStack mutation
- `components/ui/image-stream-hero.tsx` — reusable, reduced-motion-safe coastal image-stream animation used by the public hero
- `components/ui/coastal-door-reveal.tsx` — scroll-triggered coastal door reveal; it never locks the document scroll
- `components/ui/testimonials-columns-1.tsx` — Motion-powered, continuously scrolling traveller-note cards
- `lib/utils.ts` — `cn()` utility for the shadcn-compatible `/components/ui` convention
- `public/door-traveler.png` — user-provided traveller image revealed behind the interactive door
- `lib/api.ts` — backend adapter; replace only this layer as schemas mature
- `lib/types.ts` — application contracts

## Motion UI

The public page now separates the hero from its animated content: the image-stream is the first content section below the hero, followed by a scroll-triggered door reveal. `motion` is the only added dependency. All article cards have a subtle entrance and hover-lift animation, automatically disabled where users prefer reduced motion.

## Map handoff

Replace the `.map-landscape` presentation in `app/page.tsx` with a client-only MapLibre GL JS or Leaflet component. Keep map markers/route geometry as a visual confirmation layer; backend remains responsible for all safety assessment.
