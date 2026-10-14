"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRemote } from "../../../lib/use-remote";
import {
  dateTime,
  FootballStatus,
  Match,
  Report,
  Standing,
} from "../../../lib/types";
import { browseClubs } from "../../../lib/teams";
import { ErrorBox, Empty, Loading, PageTitle } from "../../../components/Ui";
import { Markdown } from "../../../components/Answer";
import { ApiError } from "../../../lib/api";
import { useApp } from "../../../components/AppProvider";
import { TeamName, FormBadges } from "../../../components/FootballIdentity";
import { recentForm } from "../../../lib/matchday";
import { seasonRounds } from "../../../lib/competition";
import { LeagueInsights } from "../../../components/LeagueInsights";
import { FixtureList } from "../../../components/FixtureList";
import { SimulationPage } from "../../../components/Simulation";
import { Trophy, CalendarDays } from "lucide-react";
const statusLabels: Record<string, string> = {
  SCHEDULED: "รอแข่งขัน",
  LIVE: "กำลังแข่งขัน",
  FINISHED: "จบการแข่งขัน",
  POSTPONED: "เลื่อนการแข่งขัน",
  CANCELLED: "ยกเลิก",
};
export default function FootballPage({
  params,
  searchParams = {},
}: {
  params: { view: string };
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  if (params.view === "simulation") return <SimulationPage />;
  const initial = new URLSearchParams();
  for (const key of ["season", "team_id", "matchweek", "status"]) {
    const value = searchParams[key];
    if (typeof value === "string") initial.set(key, value);
  }
  return (
    <FootballView
      key={params.view + initial.toString()}
      view={params.view}
      initialQuery={initial.toString()}
    />
  );
}
function FootballView({
  view,
  initialQuery,
}: {
  view: string;
  initialQuery: string;
}) {
  const app = useApp();
  const browsingId = app.browsingTeam.teamId;
  const initial = new URLSearchParams(initialQuery);
  const initialTeam =
    initial.get("team_id") === "all"
      ? ""
      : (initial.get("team_id") ?? String(browsingId));
  initial.delete("team_id");
  // Only the current season is stored, so the page never selects another one.
  initial.delete("season");
  if (view === "fixtures" && initialTeam) initial.set("team_id", initialTeam);
  const [week, setWeek] = useState(initial.get("matchweek") ?? ""),
    [team, setTeam] = useState(initialTeam),
    [status, setStatus] = useState(initial.get("status") ?? "");
  const [query, setQuery] = useState(
      initial.size ? "?" + initial.toString() : "",
    ),
    [revision, setRevision] = useState(0);
  const live = useRemote<FootballStatus>("/football/status", revision);
  const previousBrowsing = useRef(browsingId);
  useEffect(() => {
    if (previousBrowsing.current === browsingId) return;
    previousBrowsing.current = browsingId;
    setTeam(String(browsingId));
    if (view === "fixtures")
      setQuery((current) => {
        const q = new URLSearchParams(current);
        q.set("team_id", String(browsingId));
        return "?" + q;
      });
  }, [browsingId, view]);
  const selectedSeason =
    new URLSearchParams(query).get("season") || live.data?.current_season;
  const formSource = useRemote<{ matches: Match[] }>(
    view === "standings" && selectedSeason
      ? "/football/fixtures?season=" +
          encodeURIComponent(selectedSeason) +
          "&status=FINISHED"
      : null,
    revision,
  );
  const selectedWeek = new URLSearchParams(query).get("matchweek");
  const totalWeeks = seasonRounds(
    selectedSeason,
    selectedSeason === live.data?.current_season
      ? live.data?.total_matchweeks
      : null,
  );
  function moveWeek(delta: number) {
    const value = Number(selectedWeek) + delta;
    if (value < 1 || value > 38) return;
    setWeek(String(value));
    setQuery((current) => {
      const q = new URLSearchParams(current);
      q.set("matchweek", String(value));
      return "?" + q;
    });
  }
  const titles: Record<string, string> = {
    fixtures: "ผลและโปรแกรมการแข่งขัน",
    standings: "ตารางคะแนน",
    reports: "รายงานประจำสัปดาห์",
  };
  const valid = view in titles;
  const resource = useRemote<
    {
      rows?: Standing[];
      matches?: Match[];
      fetched_at?: string;
      season?: string;
    } & Partial<Report>
  >(
    valid
      ? "/football/" + (view === "reports" ? "reports/weekly" : view) + query
      : null,
    revision,
  );
  if (!valid)
    return (
      <Empty>
        ไม่พบหน้านี้ <Link href="/">กลับหน้าแรก</Link>
      </Empty>
    );
  // 404 here means nothing is stored for that season yet, not a broken page.
  const emptyResult =
    resource.error instanceof ApiError &&
    resource.error.status === 404 &&
    (view === "reports" || view === "standings");
  return (
    <div className={`football-page football-${view}`}>
      <div className="football-heading">
        <PageTitle
          eyebrow={`PREMIER LEAGUE / ${selectedSeason ?? "—"}`}
          title={titles[view]}
        />
        <div className="competition-emblem" aria-hidden="true">
          {view === "standings" ? <Trophy /> : <CalendarDays />}
          <span>
            PREMIER
            <br />
            LEAGUE
          </span>
        </div>
      </div>
      <div className="status-strip">
        <span>
          ฤดูกาล {live.data?.current_season ?? "—"} · นัดที่{" "}
          {live.data?.current_matchweek ?? "—"}
        </span>
        <span>อัปเดตล่าสุด {dateTime(live.data?.last_ingest_at)}</span>
        <button onClick={() => setRevision((value) => value + 1)}>
          รีเฟรช
        </button>
      </div>
      <ErrorBox
        error={live.error}
        retry={() => setRevision((value) => value + 1)}
      />
      {view !== "standings" && (
        <form
          className="filter-bar panel"
          onSubmit={(event) => {
            event.preventDefault();
            const search = new URLSearchParams();
            if (week) search.set("matchweek", week);
            if (view === "fixtures") {
              if (team) search.set("team_id", team);
              if (status) search.set("status", status);
            }
            setQuery(search.size ? "?" + search.toString() : "");
          }}
        >
          <label>
            นัด
            <input
              type="number"
              min={1}
              max={38}
              placeholder="ล่าสุด / ทั้งหมด"
              value={week}
              onChange={(event) => setWeek(event.target.value)}
            />
          </label>
          {view === "fixtures" && (
            <>
              <label>
                ทีม
                <select
                  value={team}
                  onChange={(event) => setTeam(event.target.value)}
                >
                  <option value="">ทุกทีม</option>
                  {browseClubs.map((item) => (
                    <option key={item.key} value={item.teamId}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                สถานะ
                <select
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                >
                  <option value="">ทุกสถานะ</option>
                  {Object.entries(statusLabels).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          <button className="primary">แสดงข้อมูล</button>
        </form>
      )}
      {view === "fixtures" && (
        <div className="round-nav">
          <button
            disabled={!selectedWeek || Number(selectedWeek) <= 1}
            onClick={() => moveWeek(-1)}
          >
            ← นัดก่อนหน้า
          </button>
          <div className="round-progress">
            <strong>
              {selectedWeek
                ? "การแข่งขันนัดที่ " +
                  selectedWeek +
                  (totalWeeks ? " จาก " + totalWeeks + " นัด" : "")
                : "ทุกนัดในช่วงที่เลือก"}
            </strong>
            {selectedWeek && totalWeeks && (
              <>
                <progress
                  aria-label="ความคืบหน้ารอบการแข่งขัน"
                  value={Number(selectedWeek)}
                  max={totalWeeks}
                />
                <small>
                  {selectedWeek}/{totalWeeks}
                </small>
              </>
            )}
          </div>
          <button
            disabled={
              !selectedWeek ||
              Number(selectedWeek) >= Math.min(totalWeeks ?? 38, 38)
            }
            onClick={() => moveWeek(1)}
          >
            นัดถัดไป →
          </button>
        </div>
      )}
      {view === "standings" && (
        <>
          <p className="form-legend">
            5 นัดล่าสุดที่มีข้อมูล · เก่า → ล่าสุด · ✓ ชนะ / − เสมอ / × แพ้ ·
            วงแหวน = นัดล่าสุด
          </p>
          <ErrorBox
            error={formSource.error}
            retry={() => setRevision((x) => x + 1)}
          />
        </>
      )}
      {resource.loading ? (
        <Loading />
      ) : emptyResult ? (
        <Empty>
          {view === "reports"
            ? "ยังไม่มีรายงานที่เผยแพร่ในช่วงที่เลือก"
            : "ยังไม่มีตารางคะแนนของฤดูกาลนี้"}
        </Empty>
      ) : resource.error ? (
        <ErrorBox
          error={resource.error}
          retry={() => setRevision((value) => value + 1)}
        />
      ) : (
        <div
          className={
            view === "standings" ? "standings-layout" : "football-results"
          }
        >
          <section
            className={`panel ${view === "standings" ? "standings-panel" : view === "fixtures" ? "fixtures-panel" : ""}`}
          >
            {resource.data?.fetched_at && (
              <p className="muted">
                ข้อมูล ณ {dateTime(resource.data.fetched_at)}
              </p>
            )}
            {view === "standings" &&
              (resource.data?.rows?.length ? (
                <div className="table-scroll">
                  <table>
                    <caption className="sr-only">
                      ตารางคะแนนพรีเมียร์ลีก
                    </caption>
                    <thead>
                      <tr>
                        {[
                          "อันดับ",
                          "ทีม",
                          "แข่ง",
                          "ชนะ",
                          "เสมอ",
                          "แพ้",
                          "ได้",
                          "เสีย",
                          "+/−",
                          "คะแนน",
                          "5 นัดที่มีข้อมูล",
                        ].map((label) => (
                          <th key={label}>{label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {resource.data.rows.map((row) => (
                        <tr
                          key={row.team_id}
                          className={
                            row.team_id === browsingId ? "club-row" : ""
                          }
                        >
                          <td>{row.position}</td>
                          <th scope="row">
                            <TeamName id={row.team_id} name={row.name} />
                          </th>
                          <td>{row.played}</td>
                          <td>{row.won}</td>
                          <td>{row.draw}</td>
                          <td>{row.lost}</td>
                          <td>{row.goals_for}</td>
                          <td>{row.goals_against}</td>
                          <td>{row.goal_difference}</td>
                          <td>
                            <strong>{row.points}</strong>
                          </td>
                          <td>
                            <FormBadges
                              teamId={row.team_id}
                              games={
                                recentForm(
                                  formSource.data?.matches ?? [],
                                  row.team_id,
                                ).games
                              }
                              results={
                                recentForm(
                                  formSource.data?.matches ?? [],
                                  row.team_id,
                                ).results
                              }
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty>ยังไม่มีตารางคะแนน</Empty>
              ))}
            {view === "fixtures" &&
              (resource.data?.matches?.length ? (
                <FixtureList
                  matches={resource.data.matches}
                  showAll={
                    new URLSearchParams(query).has("team_id")
                      ? () => {
                          setTeam("");
                          setQuery((current) => {
                            const q = new URLSearchParams(current);
                            q.delete("team_id");
                            return q.size ? "?" + q : "";
                          });
                        }
                      : undefined
                  }
                />
              ) : (
                <Empty>ไม่มีการแข่งขันตรงกับตัวกรอง</Empty>
              ))}
            {view === "reports" && resource.data?.markdown && (
              <article>
                <span className="badge">
                  นัดที่ {resource.data.matchweek} · เผยแพร่แล้ว
                </span>
                <h2>{resource.data.title}</h2>
                <p className="muted">
                  ข้อมูล ณ {dateTime(resource.data.data_as_of)}
                </p>
                <Markdown text={resource.data.markdown} />
              </article>
            )}
          </section>
          {view === "standings" && !!resource.data?.rows?.length && (
            <LeagueInsights
              rows={resource.data.rows}
              matches={formSource.data?.matches ?? []}
              teamId={browsingId}
            />
          )}
        </div>
      )}
    </div>
  );
}
