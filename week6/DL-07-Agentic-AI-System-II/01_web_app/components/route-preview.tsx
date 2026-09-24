"use client";
import { LoaderCircle, MapPin, MapPinned, MousePointerClick, Navigation, RotateCcw } from "lucide-react";
import { TripMap } from "@/components/ui/trip-map";
import { useTrip } from "@/components/trip-context";
import { haversineKm } from "@/lib/geocode";

/**
 * Trust the geometry only when its endpoints are close to the markers we placed.
 */
const ROUTE_ENDPOINT_TOLERANCE_KM = 150;

export function RoutePreview() {
  const {
    status,
    originPoint,
    destinationPoint,
    recommendation,
    roadRoutes,
    selectedRouteIndex,
    pinningMode,
    setPinningMode,
    pinLocation,
    resetPins,
  } = useTrip();

  const activeRoute =
    selectedRouteIndex > 0 && recommendation?.routes?.alternatives?.[selectedRouteIndex - 1]
      ? recommendation.routes.alternatives[selectedRouteIndex - 1]
      : recommendation?.routes?.primary;

  const rawCoordinates =
    activeRoute?.geometry && (activeRoute.geometry as { type?: string }).type === "LineString"
      ? ((activeRoute.geometry as { coordinates?: unknown }).coordinates as Array<[number, number]>)
      : null;

  const routeMatchesMarkers =
    !!rawCoordinates &&
    rawCoordinates.length >= 2 &&
    !!originPoint &&
    !!destinationPoint &&
    haversineKm(originPoint, { lat: rawCoordinates[0][1], lon: rawCoordinates[0][0] }) <=
      ROUTE_ENDPOINT_TOLERANCE_KM &&
    haversineKm(destinationPoint, {
      lat: rawCoordinates[rawCoordinates.length - 1][1],
      lon: rawCoordinates[rawCoordinates.length - 1][0],
    }) <= ROUTE_ENDPOINT_TOLERANCE_KM;

  // Every selectable road option must come from the router. Never draw the mock
  // recommendation's sparse waypoint geometry as if it were a driveable road.
  const selectedRoadRoute = roadRoutes[selectedRouteIndex] ?? roadRoutes[0] ?? null;
  const usingRoadRoute = !!selectedRoadRoute;
  const coordinates = usingRoadRoute
    ? selectedRoadRoute.coordinates
    : routeMatchesMarkers
      ? rawCoordinates
      : null;

  const distanceKm = usingRoadRoute
    ? Math.round(selectedRoadRoute.distanceKm)
    : activeRoute?.distance_km != null
      ? Math.round(activeRoute.distance_km)
      : originPoint && destinationPoint
        ? Math.round(haversineKm(originPoint, destinationPoint))
        : null;

  const showApproximateWarning = !usingRoadRoute && !routeMatchesMarkers && !!recommendation;
  const avoidLabels: Record<string, string> = {
    HIGHWAYS: "ทางด่วน",
    TOLLS: "ค่าผ่านทาง",
    FERRIES: "เรือข้ามฟาก",
  };

  const handlePinLocation = (type: "origin" | "destination", coords: { lat: number; lon: number }) => {
    void pinLocation(type, coords);
    // After pinning origin, auto-advance to destination if destination is not yet set
    if (type === "origin" && !destinationPoint) {
      setPinningMode("destination");
    } else {
      setPinningMode(null);
    }
  };

  return (
    <div className="relative h-[460px] w-full overflow-hidden rounded-2xl shadow-float bg-slate-100">
      <TripMap
        origin={originPoint}
        destination={destinationPoint}
        routeCoordinates={coordinates}
        riskLevel={recommendation?.risk?.level ?? null}
        pinningMode={pinningMode}
        onPinLocation={handlePinLocation}
      />

      {/* Floating Map Controls Toolbar (z-[1100] renders above all Leaflet layers) */}
      <div className="pointer-events-none absolute inset-x-4 top-4 z-[1100] flex flex-wrap items-center justify-between gap-2">
        <div className="pointer-events-auto flex items-center gap-1.5 rounded-xl bg-white/95 p-1.5 shadow-lg backdrop-blur border border-slate-200/80">
          <button
            type="button"
            onClick={() => setPinningMode(pinningMode === "origin" ? null : "origin")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
              pinningMode === "origin"
                ? "bg-aqua text-white shadow-sm ring-2 ring-aqua/30"
                : "text-slate-700 hover:bg-slate-100 hover:text-ink"
            }`}
          >
            <Navigation size={13} className={pinningMode === "origin" ? "text-white" : "text-[#0e7490]"} />
            <span>ปักหมุดต้นทาง (A)</span>
          </button>

          <button
            type="button"
            onClick={() => setPinningMode(pinningMode === "destination" ? null : "destination")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
              pinningMode === "destination"
                ? "bg-amber-600 text-white shadow-sm ring-2 ring-amber-500/30"
                : "text-slate-700 hover:bg-slate-100 hover:text-ink"
            }`}
          >
            <MapPin size={13} className={pinningMode === "destination" ? "text-white" : "text-amber-600"} />
            <span>ปักหมุดปลายทาง (B)</span>
          </button>

          {(originPoint || destinationPoint) && (
            <button
              type="button"
              onClick={resetPins}
              title="ล้างหมุดบนแผนที่"
              className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-red-600 transition"
            >
              <RotateCcw size={12} />
              <span className="hidden sm:inline">รีเซ็ต</span>
            </button>
          )}
        </div>

        {/* Pinning active helper pill */}
        {pinningMode && (
          <div className="pointer-events-auto flex items-center gap-1.5 rounded-full bg-ink/90 px-3.5 py-1.5 text-xs font-medium text-white shadow-lg backdrop-blur border border-white/20 animate-fade-in">
            <MousePointerClick size={14} className="text-aqua animate-bounce" />
            <span>คลิกบนแผนที่เพื่อระบุ{pinningMode === "origin" ? "จุดเริ่มต้น (A)" : "จุดปลายทาง (B)"}</span>
          </div>
        )}
      </div>

      {/* Non-intrusive bottom-center prompt when empty */}
      {!originPoint && !destinationPoint && !pinningMode && (
        <div className="pointer-events-none absolute bottom-4 inset-x-4 flex justify-center z-[1100]">
          <div className="flex items-center gap-2 rounded-xl bg-white/95 px-4 py-2.5 text-xs font-medium text-slate-600 shadow-lg backdrop-blur border border-slate-200/70">
            <span>💡 คลิกปุ่ม <b>&ldquo;ปักหมุดต้นทาง (A)&rdquo;</b> ด้านบน หรือพิมพ์ชื่อในแบบฟอร์มเพื่อเริ่มสำรวจ</span>
          </div>
        </div>
      )}

      {(status === "geocoding" || status === "submitting" || status === "streaming") && (
        <div className="absolute inset-x-5 top-16 z-[1100] flex items-center gap-2 rounded-xl bg-white/95 px-4 py-3 text-xs font-bold text-ink shadow-lg backdrop-blur border border-slate-200/60">
          <LoaderCircle className="animate-spin text-aqua" size={16} />
          {status === "geocoding" ? "กำลังค้นหาตำแหน่งบนแผนที่…" : "กำลังประเมินความเสี่ยง…"}
        </div>
      )}

      {originPoint && destinationPoint && (
        <div className="absolute bottom-5 left-5 z-[1100] rounded-xl bg-white/95 p-4 text-xs text-ink shadow-lg backdrop-blur border border-slate-200/60">
          <div className="flex items-center gap-2 font-bold">
            <MapPinned size={16} className="text-aqua" /> Route preview
          </div>
          <p className="mt-1 text-slate-600">
            <b className="text-ink">{originPoint.name}</b> → <b className="text-ink">{destinationPoint.name}</b>
            {distanceKm != null ? ` · ${distanceKm} km` : ""}
          </p>
          {usingRoadRoute && selectedRoadRoute.appliedAvoid.length > 0 && (
            <p className="mt-1 text-[11px] font-semibold text-emerald-700">
              คำนวณใหม่โดยเลี่ยง {selectedRoadRoute.appliedAvoid.map((item) => avoidLabels[item] ?? item).join(", ")}
            </p>
          )}
          {showApproximateWarning && (
            <p className="mt-1 text-[11px] text-amber-600">
              เส้นทางเป็นเส้นประมาณระยะทาง ยังไม่ใช่เส้นทางถนนจริง
            </p>
          )}
        </div>
      )}
    </div>
  );
}
