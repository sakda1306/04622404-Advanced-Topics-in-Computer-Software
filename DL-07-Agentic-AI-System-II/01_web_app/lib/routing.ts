export type RoutePoint = [number, number]; // [lon, lat], matches GeoJSON order

export type DrivingRoute = {
  coordinates: RoutePoint[];
  distanceKm: number;
  durationMinutes: number;
  appliedAvoid: string[];
};

/**
 * Ask our server-side routing proxy for road geometry. Keeping the provider behind
 * a Route Handler avoids browser CORS failures and, importantly, lets the map route
 * use the same avoidance preferences as the recommendation request.
 */
export async function fetchDrivingRoutes(
  origin: { lat: number; lon: number },
  destination: { lat: number; lon: number },
  avoid: string[] = [],
  signal?: AbortSignal,
): Promise<DrivingRoute[]> {
  try {
    const params = new URLSearchParams({
      origin: `${origin.lat},${origin.lon}`,
      destination: `${destination.lat},${destination.lon}`,
    });
    for (const option of avoid) params.append("avoid", option);
    const response = await fetch(`/api/route?${params.toString()}`, { signal });
    if (!response.ok) return [];
    const data = (await response.json()) as { routes?: Array<Partial<DrivingRoute>> };
    return (data.routes ?? []).flatMap((route) =>
      route.coordinates && route.coordinates.length >= 2
        ? [{
            coordinates: route.coordinates,
            distanceKm: route.distanceKm ?? 0,
            durationMinutes: route.durationMinutes ?? 0,
            appliedAvoid: route.appliedAvoid ?? [],
          }]
        : [],
    );
  } catch {
    // Network error, CORS, or the demo server is throttling us — caller falls back.
    return [];
  }
}
