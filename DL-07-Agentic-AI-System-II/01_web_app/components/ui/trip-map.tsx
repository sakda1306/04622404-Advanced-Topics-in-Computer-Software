"use client";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import type { Map as LeafletMap, LayerGroup } from "leaflet";
import type { GeoPoint } from "@/lib/geocode";
import type { RiskLevel } from "@/lib/types";

const RISK_COLOR: Record<RiskLevel, string> = {
  LOW: "#0f766e",
  MEDIUM: "#b45309",
  HIGH: "#b91c1c",
};

function dot(color: string, letter: string) {
  return `<span style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:9999px;background:${color};color:#fff;font-size:12px;font-weight:700;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,.35)">${letter}</span>`;
}

export function TripMap({
  origin,
  destination,
  routeCoordinates,
  riskLevel,
  pinningMode = null,
  onPinLocation,
}: {
  origin: GeoPoint | null;
  destination: GeoPoint | null;
  routeCoordinates?: Array<[number, number]> | null;
  riskLevel: RiskLevel | null;
  pinningMode?: "origin" | "destination" | null;
  onPinLocation?: (type: "origin" | "destination", coords: { lat: number; lon: number }) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const layerRef = useRef<LayerGroup | null>(null);
  const [ready, setReady] = useState(false);

  // Keep latest callbacks/mode in ref for map events without recreating map
  const pinRef = useRef({ pinningMode, onPinLocation });
  pinRef.current = { pinningMode, onPinLocation };

  useEffect(() => {
    let cancelled = false;
    let resizeObserver: ResizeObserver | null = null;

    void import("leaflet").then((leaflet) => {
      if (cancelled || !containerRef.current || mapRef.current) return;
      const L = leaflet.default;
      const map = L.map(containerRef.current, {
        scrollWheelZoom: false,
        fadeAnimation: false,
        zoomControl: false,
      }).setView([13.7563, 100.5018], 6);

      L.control.zoom({ position: "bottomright" }).addTo(map);

      // Longdo Map Tiles (native Thai roads, landmarks, and soi names)
      const longdoKey = process.env.NEXT_PUBLIC_LONGDO_MAP_KEY || "";
      const longdoTileUrl = longdoKey
        ? `https://ms.longdo.com/mmmap/img.php?proj=epsg3857&mode=normal&zoom={z}&x={x}&y={y}&HD=1&key=${longdoKey}`
        : "https://ms.longdo.com/mmmap/img.php?proj=epsg3857&mode=normal&zoom={z}&x={x}&y={y}&HD=1";

      L.tileLayer(longdoTileUrl, {
        attribution: '&copy; <a href="https://map.longdo.com/" target="_blank" rel="noreferrer">Longdo Map</a>',
        maxZoom: 19,
        minZoom: 1,
      }).addTo(map);

      // Handle map click for pinning
      map.on("click", (e: import("leaflet").LeafletMouseEvent) => {
        const { pinningMode, onPinLocation } = pinRef.current;
        if (pinningMode && onPinLocation) {
          onPinLocation(pinningMode, { lat: e.latlng.lat, lon: e.latlng.lng });
        }
      });

      layerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;

      // Ensure Leaflet calculates dimensions immediately
      setTimeout(() => {
        if (!cancelled && mapRef.current) {
          mapRef.current.invalidateSize();
        }
      }, 100);

      if (containerRef.current) {
        resizeObserver = new ResizeObserver(() => {
          if (mapRef.current) {
            mapRef.current.invalidateSize();
          }
        });
        resizeObserver.observe(containerRef.current);
      }

      setReady(true);
    });

    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!ready || !mapRef.current || !layerRef.current) return;
    void import("leaflet").then((leaflet) => {
      const L = leaflet.default;
      const map = mapRef.current;
      const group = layerRef.current;
      if (!map || !group) return;
      group.clearLayers();

      const color = riskLevel ? RISK_COLOR[riskLevel] : "#0e7490";
      const points: Array<[number, number]> = [];

      if (origin) {
        const markerA = L.marker([origin.lat, origin.lon], {
          draggable: true,
          icon: L.divIcon({ html: dot("#0e7490", "A"), className: "", iconSize: [28, 28] }),
        })
          .bindTooltip(`<b>ต้นทาง (A):</b> ${origin.name}<br/><span style="font-size:10px;color:#cbd5e1">ลากเพื่อย้ายตำแหน่ง</span>`, {
            direction: "top",
            offset: [0, -14],
          })
          .addTo(group);

        markerA.on("dragend", () => {
          const pos = markerA.getLatLng();
          pinRef.current.onPinLocation?.("origin", { lat: pos.lat, lon: pos.lng });
        });

        points.push([origin.lat, origin.lon]);
      }

      if (destination) {
        const markerB = L.marker([destination.lat, destination.lon], {
          draggable: true,
          icon: L.divIcon({ html: dot(color, "B"), className: "", iconSize: [28, 28] }),
        })
          .bindTooltip(`<b>ปลายทาง (B):</b> ${destination.name}<br/><span style="font-size:10px;color:#cbd5e1">ลากเพื่อย้ายตำแหน่ง</span>`, {
            direction: "top",
            offset: [0, -14],
          })
          .addTo(group);

        markerB.on("dragend", () => {
          const pos = markerB.getLatLng();
          pinRef.current.onPinLocation?.("destination", { lat: pos.lat, lon: pos.lng });
        });

        points.push([destination.lat, destination.lon]);
      }

      const line = routeCoordinates?.map(([lon, lat]) => [lat, lon] as [number, number]) ??
        (points.length === 2 ? points : null);
      if (line && line.length >= 2) {
        L.polyline(line, { color, weight: 4, opacity: 0.85, dashArray: "1 8", lineCap: "round" }).addTo(
          group,
        );
      }

      map.invalidateSize();
      if (points.length > 0) {
        map.fitBounds(L.latLngBounds(line ?? points), { padding: [48, 48], maxZoom: 14 });
      }
    });
  }, [ready, origin, destination, routeCoordinates, riskLevel]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={
        origin && destination
          ? `แผนที่แสดงเส้นทางจาก ${origin.name} ไปยัง ${destination.name}`
          : "แผนที่แสดงตำแหน่งต้นทางและปลายทาง"
      }
      style={{ cursor: pinningMode ? "crosshair" : undefined }}
      className="h-full min-h-[440px] w-full"
    />
  );
}
