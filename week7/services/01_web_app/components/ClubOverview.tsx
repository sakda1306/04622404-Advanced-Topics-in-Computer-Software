"use client";
import Link from "next/link";
import { useApp } from "./AppProvider";
import { useRemote } from "../lib/use-remote";
import { dateTime, Match, Standing } from "../lib/types";
import { TeamCrest } from "./FootballIdentity";
import { teamFromId } from "../lib/teams";
import { ErrorBox, Loading } from "./Ui";

const Crest = TeamCrest;
export function ClubOverview() {
  const app = useApp();
  const team = app.browsingTeam ?? app.team;
  const fixtures = useRemote<{ matches: Match[] }>(
    "/football/fixtures?team_id=" + team.teamId,
  );
  const standings = useRemote<{ rows: Standing[]; season?: string }>(
    "/football/standings",
  );
  const matches = (fixtures.data?.matches ?? []).filter(
    (m) => m.home.team_id === team.teamId || m.away.team_id === team.teamId,
  );
  const now = Date.now();
  const valid = matches.filter((m) => Number.isFinite(Date.parse(m.kickoff)));
  const latest = (items: Match[]) =>
    [...items].sort((a, b) => Date.parse(b.kickoff) - Date.parse(a.kickoff))[0];
  const live = latest(valid.filter((m) => m.status === "LIVE"));
  const next = valid
    .filter((m) => m.status === "SCHEDULED" && Date.parse(m.kickoff) >= now)
    .sort((a, b) => Date.parse(a.kickoff) - Date.parse(b.kickoff))[0];
  const finished = latest(
    valid.filter(
      (m) => m.status === "FINISHED" && Date.parse(m.kickoff) <= now,
    ),
  );
  const match = live ?? next ?? finished;
  const rows = [...(standings.data?.rows ?? [])]
    .sort((a, b) => a.position - b.position)
    .slice(0, 5);
  return (
    <>
      <section className="panel match-preview companion-card">
        <h2>{live ? "LIVE MATCH" : next ? "NEXT MATCH" : "MATCH CENTRE"}</h2>
        <small>
          {live
            ? "กำลังแข่งขัน"
            : next
              ? "นัดถัดไป"
              : finished
                ? "ผลการแข่งขันล่าสุด"
                : "การแข่งขันของทีมคุณ"}
        </small>
        {fixtures.loading ? (
          <Loading />
        ) : fixtures.error ? (
          <ErrorBox error={fixtures.error} />
        ) : match ? (
          <Link
            className="match-pair"
            href={"/matches/" + encodeURIComponent(match.match_id)}
          >
            <span>
              <Crest id={match.home.team_id} name={match.home.name} />
              <strong>
                {teamFromId(match.home.team_id)?.shortName ?? match.home.name}
              </strong>
            </span>
            <b>
              {["FINISHED", "LIVE"].includes(match.status)
                ? `${match.score.home ?? "—"} : ${match.score.away ?? "—"}`
                : "VS"}
            </b>
            <span>
              <Crest id={match.away.team_id} name={match.away.name} />
              <strong>
                {teamFromId(match.away.team_id)?.shortName ?? match.away.name}
              </strong>
            </span>
          </Link>
        ) : (
          <p className="match-empty">ยังไม่มีการแข่งขันที่พร้อมแสดง</p>
        )}
        {match && <small>{dateTime(match.kickoff)}</small>}
      </section>
      <section className="panel league-preview">
        <h2>LEAGUE SNAPSHOT</h2>
        <small>พรีเมียร์ลีก {standings.data?.season ?? ""}</small>
        {standings.loading ? (
          <Loading />
        ) : standings.error ? (
          <ErrorBox error={standings.error} />
        ) : rows.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>ทีม</th>
                  <th>P</th>
                  <th>GD</th>
                  <th>PTS</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.team_id}
                    className={row.team_id === team.teamId ? "club-row" : ""}
                  >
                    <td>{row.position}</td>
                    <td>
                      <span className="table-club">
                        <Crest id={row.team_id} name={row.name} />
                        {teamFromId(row.team_id)?.shortName ?? row.name}
                      </span>
                    </td>
                    <td>{row.played}</td>
                    <td>{row.goal_difference}</td>
                    <td>
                      <strong>{row.points}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>ยังไม่มีตารางคะแนน</p>
        )}
        <Link className="text-link" href="/football/standings">
          ดูตารางคะแนนทั้งหมด →
        </Link>
      </section>
    </>
  );
}
