"use client";
import Link from "next/link";
import { ChevronRight, MapPin, List } from "lucide-react";
import { Match } from "../lib/types";
import { TeamName } from "./FootballIdentity";
const labels: Record<string, string> = {
  FINISHED: "จบการแข่งขัน",
  LIVE: "กำลังแข่งขัน",
  SCHEDULED: "รอแข่งขัน",
  POSTPONED: "เลื่อนการแข่งขัน",
  CANCELLED: "ยกเลิก",
};
export function FixtureList({
  matches,
  showAll,
}: {
  matches: Match[];
  showAll?: () => void;
}) {
  const groups = new Map<string, Match[]>();
  [...matches]
    .sort((a, b) => Date.parse(a.kickoff) - Date.parse(b.kickoff))
    .forEach((match) => {
      const date = new Date(match.kickoff).toLocaleDateString("th-TH", {
        timeZone: "Asia/Bangkok",
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      });
      groups.set(date, [...(groups.get(date) ?? []), match]);
    });
  return (
    <div className="fixture-groups">
      {[...groups].map(([date, games]) => (
        <section key={date} className="panel fixture-day">
          <h2>{date}</h2>
          {games.map((match) => (
            <Link
              className="fixture-card"
              href={`/matches/${match.match_id}`}
              key={match.match_id}
            >
              <time dateTime={match.kickoff}>
                {new Date(match.kickoff).toLocaleTimeString("th-TH", {
                  timeZone: "Asia/Bangkok",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
                <small>เวลาไทย</small>
              </time>
              <TeamName id={match.home.team_id} name={match.home.name} />
              <div className="fixture-score">
                <strong>
                  {["FINISHED", "LIVE"].includes(match.status)
                    ? `${match.score.home ?? "—"} : ${match.score.away ?? "—"}`
                    : "VS"}
                </strong>
                <small>{labels[match.status] ?? match.status}</small>
              </div>
              <TeamName id={match.away.team_id} name={match.away.name} />
              <div className="fixture-meta">
                {match.venue?.name && (
                  <span>
                    <MapPin size={14} />
                    {match.venue.name}
                  </span>
                )}
                <small>นัดที่ {match.matchweek}</small>
                <ChevronRight size={18} />
              </div>
            </Link>
          ))}
          <footer className="fixture-day-footer">
            <span>แสดง {games.length} คู่</span>
            {showAll && (
              <button onClick={showAll}>
                <List size={18} />
                ดูทุกทีมในช่วงนี้
                <ChevronRight size={18} />
              </button>
            )}
          </footer>
        </section>
      ))}
    </div>
  );
}
