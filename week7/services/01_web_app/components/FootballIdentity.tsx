"use client";
import { Shield } from "lucide-react";
import { useState } from "react";
import Link from "next/link";
import { Match, dateTime } from "../lib/types";
export function TeamCrest({
  id,
  name,
  size = 28,
}: {
  id: number;
  name: string;
  size?: number;
}) {
  const [failed, setFailed] = useState<number>();
  return failed === id || !Number.isInteger(id) ? (
    <span
      className="crest-fallback"
      aria-hidden="true"
      style={{ width: size, height: size }}
    >
      <Shield size={size} />
    </span>
  ) : (
    <img
      className="club-crest"
      src={`/crests/${id}.png`}
      alt=""
      width={size}
      height={size}
      onError={() => setFailed(id)}
    />
  );
}
export function TeamName({ id, name }: { id: number; name: string }) {
  return (
    <span className="team-name">
      <TeamCrest id={id} name={name} />
      <span>{name}</span>
    </span>
  );
}
export const formLabels = { W: "ชนะ", D: "เสมอ", L: "แพ้" } as const;
export type Outcome = keyof typeof formLabels;
export function FormBadges({
  results,
  latest = true,
  games,
  teamId,
}: {
  results: Outcome[];
  latest?: boolean;
  games?: Match[];
  teamId?: number;
}) {
  return (
    <span className="form-badges" aria-label="ฟอร์มเรียงจากเก่าไปล่าสุด">
      {results.length
        ? results.slice(-5).map((value, index, array) => {
            const game = games?.slice(-5)[index];
            const label = `${formLabels[value]}${latest && index === array.length - 1 ? " · นัดล่าสุด" : ""}`;
            const detail = game
              ? `${game.home.name} ${game.score.home}–${game.score.away} ${game.away.name} · ${dateTime(game.kickoff)}`
              : "";
            return game && teamId ? (
              <Link
                key={game.match_id}
                className={`form-dot ${value} ${latest && index === array.length - 1 ? "latest" : ""}`}
                href={`/matches/${game.match_id}`}
                aria-label={`${label}: ${detail}`}
                title={`${label}: ${detail}`}
              >
                <span aria-hidden="true">
                  {value === "W" ? "✓" : value === "D" ? "−" : "×"}
                </span>
                <span className="form-tooltip">{detail}</span>
              </Link>
            ) : (
              <span
                key={index}
                role="img"
                aria-label={`${formLabels[value]}${latest && index === array.length - 1 ? " · นัดล่าสุด" : ""}`}
                title={formLabels[value]}
                className={`form-dot ${value} ${latest && index === array.length - 1 ? "latest" : ""}`}
              >
                {value === "W" ? "✓" : value === "D" ? "−" : "×"}
              </span>
            );
          })
        : "—"}
    </span>
  );
}
export function parseForm(value?: string | null): Outcome[] {
  return (value?.toUpperCase().match(/[WDL]/g) ?? []).slice(-5) as Outcome[];
}
