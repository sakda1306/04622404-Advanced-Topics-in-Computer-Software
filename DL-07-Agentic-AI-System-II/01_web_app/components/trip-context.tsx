"use client";
import { createContext, useCallback, useContext, useRef, useState } from "react";
import { requestRecommendation } from "@/lib/api";
import { toUserMessage } from "@/lib/api/problem";
import { geocode, reverseGeocode, type GeoPoint } from "@/lib/geocode";
import { buildMockRecommendation } from "@/lib/mock-recommendation";
import { fetchDrivingRoutes, type DrivingRoute } from "@/lib/routing";
import type { AvoidOption, RecommendationResponse, TravelMode } from "@/lib/types";

/** Travel modes OSRM's public driving profile can approximate with a real road route. */
const ROAD_MODES = new Set<TravelMode>(["CAR", "BUS"]);

export type TripStatus = "idle" | "geocoding" | "submitting" | "streaming" | "success" | "error";
export type PinningMode = "origin" | "destination" | null;

export type TripFormInput = {
  origin: string;
  destination: string;
  date: string;
  time?: string;
  mode: TravelMode;
  avoid?: AvoidOption[];
  travelerCount?: number;
  note?: string;
};

type TripContextValue = {
  status: TripStatus;
  originPoint: GeoPoint | null;
  destinationPoint: GeoPoint | null;
  recommendation: RecommendationResponse | null;
  usingMock: boolean;
  progressMessage: string | null;
  errorMessage: string | null;
  selectedRouteIndex: number;
  setSelectedRouteIndex: (index: number) => void;
  /** Real road-following geometry for CAR/BUS, fetched independently of the recommendation. */
  roadRoutes: DrivingRoute[];
  lastInput: TripFormInput | null;
  submit: (input: TripFormInput) => Promise<void>;
  applyAssistantChanges: (changes: Partial<TripFormInput>) => Promise<void>;
  pinningMode: PinningMode;
  setPinningMode: (mode: PinningMode) => void;
  pinLocation: (type: "origin" | "destination", coords: { lat: number; lon: number }) => Promise<void>;
  resetPins: () => void;
};

const TripContext = createContext<TripContextValue | null>(null);

export function TripProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<TripStatus>("idle");
  const [lastInput, setLastInput] = useState<TripFormInput | null>(null);
  const [originPoint, setOriginPoint] = useState<GeoPoint | null>(null);
  const [destinationPoint, setDestinationPoint] = useState<GeoPoint | null>(null);
  const [pinningMode, setPinningMode] = useState<PinningMode>(null);
  const [recommendation, setRecommendation] = useState<RecommendationResponse | null>(null);
  const [usingMock, setUsingMock] = useState(false);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [roadRoutes, setRoadRoutes] = useState<DrivingRoute[]>([]);
  const [selectedRouteIndex, setSelectedRouteIndex] = useState(0);
  const requestSeq = useRef(0);

  const resetPins = useCallback(() => {
    setOriginPoint(null);
    setDestinationPoint(null);
    setRoadRoutes([]);
    setPinningMode(null);
  }, []);

  const pinLocation = useCallback(async (type: "origin" | "destination", coords: { lat: number; lon: number }) => {
    const initialName = `พิกัด (${coords.lat.toFixed(4)}, ${coords.lon.toFixed(4)})`;
    const newPoint: GeoPoint = {
      lat: coords.lat,
      lon: coords.lon,
      name: initialName,
      source: "nominatim",
    };

    if (type === "origin") {
      setOriginPoint(newPoint);
    } else {
      setDestinationPoint(newPoint);
    }

    // Resolve human-readable name in background
    reverseGeocode(coords.lat, coords.lon).then((resolvedName) => {
      const updatedPoint: GeoPoint = {
        lat: coords.lat,
        lon: coords.lon,
        name: resolvedName,
        source: "nominatim",
      };
      if (type === "origin") {
        setOriginPoint((prev) => (prev && prev.lat === coords.lat && prev.lon === coords.lon ? updatedPoint : prev));
      } else {
        setDestinationPoint((prev) => (prev && prev.lat === coords.lat && prev.lon === coords.lon ? updatedPoint : prev));
      }
    });

    // Update road route if both endpoints exist
    const otherPoint = type === "origin" ? destinationPoint : originPoint;
    if (otherPoint) {
      const start = type === "origin" ? newPoint : otherPoint;
      const end = type === "origin" ? otherPoint : newPoint;
      fetchDrivingRoutes(start, end, lastInput?.avoid).then((routes) => {
        setRoadRoutes(routes);
      });
    }
  }, [originPoint, destinationPoint, lastInput?.avoid]);

  const submit = useCallback(async (input: TripFormInput) => {
    setLastInput(input);
    const seq = ++requestSeq.current;
    const isStale = () => seq !== requestSeq.current;

    setStatus("geocoding");
    setErrorMessage(null);
    setProgressMessage(null);
    setRoadRoutes([]);
    setSelectedRouteIndex(0);

    let origin: GeoPoint;
    let destination: GeoPoint;
    try {
      const originPromise = originPoint && originPoint.name === input.origin
        ? Promise.resolve(originPoint)
        : geocode(input.origin);
      const destPromise = destinationPoint && destinationPoint.name === input.destination
        ? Promise.resolve(destinationPoint)
        : geocode(input.destination);
      [origin, destination] = await Promise.all([originPromise, destPromise]);
    } catch {
      // geocode() already falls back internally; this only triggers on a thrown bug.
      if (isStale()) return;
      setStatus("error");
      setErrorMessage("ไม่สามารถระบุตำแหน่งจากชื่อสถานที่ได้");
      return;
    }
    if (isStale()) return;
    setOriginPoint(origin);
    setDestinationPoint(destination);
    setStatus("submitting");

    if (ROAD_MODES.has(input.mode)) {
      fetchDrivingRoutes(origin, destination, input.avoid).then((routes) => {
        if (!isStale()) setRoadRoutes(routes);
      });
    }

    const departureTime = `${input.date}T${input.time || "08:00"}:00+07:00`;

    try {
      const result = await requestRecommendation(
        {
          origin: { name: origin.name, lat: origin.lat, lon: origin.lon },
          destination: { name: destination.name, lat: destination.lat, lon: destination.lon },
          departure_time: departureTime,
          timezone: "Asia/Bangkok",
          preferences: {
            travel_modes: [input.mode],
            avoid: input.avoid && input.avoid.length > 0 ? input.avoid : undefined,
            traveler_count: input.travelerCount,
          },
          question: input.note || null,
        },
        {
          onProgress: (message) => {
            if (!isStale()) {
              setStatus("streaming");
              setProgressMessage(message);
            }
          },
        },
      );
      if (isStale()) return;
      setRecommendation(result);
      setUsingMock(false);
      setStatus("success");
    } catch (err) {
      if (isStale()) return;
      setErrorMessage(toUserMessage(err));
      setRecommendation(
        buildMockRecommendation({ origin, destination, mode: input.mode, departureTime }),
      );
      setUsingMock(true);
      setStatus("success");
    }
  }, [originPoint, destinationPoint]);

  const applyAssistantChanges = useCallback(
    async (changes: Partial<TripFormInput>) => {
      const fallback: TripFormInput = {
        origin: originPoint?.name || "Bangkok",
        destination: destinationPoint?.name || "Chiang Mai",
        date: new Date().toISOString().split("T")[0],
        time: "08:00",
        mode: "CAR",
      };
      const merged: TripFormInput = {
        ...(lastInput || fallback),
        ...changes,
      };
      setLastInput(merged);
      await submit(merged);
    },
    [lastInput, originPoint, destinationPoint, submit]
  );

  return (
    <TripContext.Provider
      value={{
        status,
        originPoint,
        destinationPoint,
        recommendation,
        usingMock,
        progressMessage,
        errorMessage,
        selectedRouteIndex,
        setSelectedRouteIndex,
        roadRoutes,
        lastInput,
        submit,
        applyAssistantChanges,
        pinningMode,
        setPinningMode,
        pinLocation,
        resetPins,
      }}
    >
      {children}
    </TripContext.Provider>
  );
}

export function useTrip(): TripContextValue {
  const ctx = useContext(TripContext);
  if (!ctx) throw new Error("useTrip must be used within TripProvider");
  return ctx;
}
