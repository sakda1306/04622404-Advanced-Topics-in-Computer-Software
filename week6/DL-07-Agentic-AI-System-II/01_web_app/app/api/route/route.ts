import { NextRequest, NextResponse } from "next/server";

const VALHALLA_URL = process.env.ROUTING_API_URL ?? "https://valhalla1.openstreetmap.de/route";
const SPATIAL_AVOID = new Set(["HIGHWAYS", "TOLLS", "FERRIES"]);

type Point = { lat: number; lon: number };

function parsePoint(value: string | null): Point | null {
  if (!value) return null;
  const [lat, lon, extra] = value.split(",").map(Number);
  if (extra !== undefined || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
}

function validCoordinates(value: unknown): value is Array<[number, number]> {
  return Array.isArray(value) && value.length >= 2 && value.every(
    (point) => Array.isArray(point) && point.length >= 2 &&
      Number.isFinite(point[0]) && Number.isFinite(point[1]),
  );
}

/** Decode Valhalla's precision-6 polyline and return GeoJSON-order [lon, lat]. */
function decodePolyline6(shape: string): Array<[number, number]> {
  const coordinates: Array<[number, number]> = [];
  let index = 0;
  let lat = 0;
  let lon = 0;
  while (index < shape.length) {
    const deltas: number[] = [];
    for (let axis = 0; axis < 2; axis += 1) {
      let result = 0;
      let shift = 0;
      let byte: number;
      do {
        if (index >= shape.length) return [];
        byte = shape.charCodeAt(index++) - 63;
        result |= (byte & 0x1f) << shift;
        shift += 5;
      } while (byte >= 0x20);
      deltas.push((result & 1) !== 0 ? ~(result >> 1) : result >> 1);
    }
    lat += deltas[0];
    lon += deltas[1];
    coordinates.push([lon / 1e6, lat / 1e6]);
  }
  return coordinates;
}

export async function GET(request: NextRequest) {
  const origin = parsePoint(request.nextUrl.searchParams.get("origin"));
  const destination = parsePoint(request.nextUrl.searchParams.get("destination"));
  if (!origin || !destination) {
    return NextResponse.json({ error: "origin and destination must be valid lat,lon pairs" }, { status: 400 });
  }

  const appliedAvoid = [...new Set(request.nextUrl.searchParams.getAll("avoid"))]
    .filter((option) => SPATIAL_AVOID.has(option));
  const costingOptions: Record<string, number> = {};
  if (appliedAvoid.includes("HIGHWAYS")) costingOptions.use_highways = 0;
  if (appliedAvoid.includes("TOLLS")) costingOptions.use_tolls = 0;
  if (appliedAvoid.includes("FERRIES")) costingOptions.use_ferry = 0;

  try {
    const upstream = await fetch(VALHALLA_URL, {
      method: "POST",
      headers: { "content-type": "application/json", "user-agent": "team-d-travel-safety/1.0" },
      body: JSON.stringify({
        locations: [origin, destination],
        costing: "auto",
        costing_options: { auto: costingOptions },
        units: "kilometers",
        shape_format: "polyline6",
        alternates: 1,
      }),
      signal: AbortSignal.timeout(12_000),
      cache: "no-store",
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: "routing provider unavailable" }, { status: 502 });
    }

    type Trip = { summary?: { length?: number; time?: number }; legs?: Array<{ shape?: unknown }> };
    const data = await upstream.json() as {
      trip?: Trip;
      alternates?: Array<{ trip?: Trip }>;
    };
    const trips = [data.trip, ...(data.alternates ?? []).map((item) => item.trip)].filter(
      (trip): trip is Trip => !!trip,
    );
    const routes = trips.flatMap((trip) => {
      const shape = trip.legs?.[0]?.shape;
      const coordinates = typeof shape === "string"
        ? decodePolyline6(shape)
        : shape && typeof shape === "object" && "coordinates" in shape
          ? (shape as { coordinates?: unknown }).coordinates
          : shape;
      return validCoordinates(coordinates)
        ? [{
            coordinates,
            distanceKm: trip.summary?.length ?? 0,
            durationMinutes: (trip.summary?.time ?? 0) / 60,
            appliedAvoid,
          }]
        : [];
    });
    if (routes.length === 0) {
      return NextResponse.json({ error: "routing provider returned invalid geometry" }, { status: 502 });
    }

    return NextResponse.json({ routes });
  } catch {
    return NextResponse.json({ error: "routing provider unavailable" }, { status: 502 });
  }
}
