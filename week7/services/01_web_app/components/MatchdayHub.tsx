"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Bookmark,
  ArrowUpRight,
  MessageCircle,
  CalendarDays,
  BarChart3,
  FileText,
  Trophy,
} from "lucide-react";
import { useApp } from "./AppProvider";
import { useRemote } from "../lib/use-remote";
import { Match, FootballStatus, dateTime } from "../lib/types";
import {
  nextMatch,
  clubMatches,
  recentForm,
  oldestEvidenceTime,
  readSavedMatches,
  SavedMatch,
} from "../lib/matchday";
import { TeamCrest, TeamName, FormBadges } from "./FootballIdentity";
import { ErrorBox, Loading } from "./Ui";
import { Prediction } from "./Prediction";
import { SeasonOutlook } from "./Simulation";
import { SavedMatches } from "./SavedMatches";
import { seasonRounds } from "../lib/competition";
export function MatchdayHub() {
  const app = useApp();
  return <Hub key={app.user?.id ?? "guest"} />;
}
function Hub() {
  const app = useApp();
  const team = app.browsingTeam;
  const [revision, setRevision] = useState(0);
  const live = useRemote<FootballStatus>("/football/status", revision);
  const season = live.data?.current_season;
  const fixtures = useRemote<{ matches: Match[] }>(
    season ? `/football/fixtures?season=${encodeURIComponent(season)}` : null,
    revision,
  );
  const [saved, setSaved] = useState<SavedMatch[]>([]);
  const [storageError, setStorageError] = useState("");
  const [ready, setReady] = useState(false);
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 60000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (app.user) {
      setSaved(readSavedMatches(app.user.id));
      setReady(true);
    }
  }, [app.user?.id]);
  function toggle(item: SavedMatch) {
    if (!app.user || !ready) return;
    const exists = saved.some((match) => match.match_id === item.match_id);
    if (!exists && saved.length >= 20) {
      setStorageError("บันทึกได้สูงสุด 20 แมตช์ กรุณาลบบางรายการก่อน");
      return;
    }
    const next = exists
      ? saved.filter((match) => match.match_id !== item.match_id)
      : [item, ...saved];
    try {
      localStorage.setItem(
        `panball:saved:v1:${app.user.id}`,
        JSON.stringify(next),
      );
      setSaved(next);
      setStorageError("");
    } catch {
      setStorageError("บันทึกไม่สำเร็จ เบราว์เซอร์ไม่อนุญาตให้เก็บข้อมูล");
    }
  }
  const matches = (fixtures.data?.matches ?? []).filter(
    (match) => match.season === season,
  );
  const next = nextMatch(matches, team.teamId, clock);
  const cutoff = next ? Math.min(clock, Date.parse(next.kickoff)) : clock;
  const opponent =
    next && (next.home.team_id === team.teamId ? next.away : next.home);
  const first = recentForm(matches, team.teamId, cutoff);
  const second = opponent
    ? recentForm(matches, opponent.team_id, cutoff)
    : null;
  const latest = recentForm(matches, team.teamId, clock).games.at(-1);
  const currentLive = clubMatches(matches, team.teamId)
    .filter((m) => m.status === "LIVE")
    .at(-1);
  const featured = currentLive ?? next ?? latest;
  const evidence = [
    ...new Map(
      [...first.games, ...(second?.games ?? [])].map((match) => [
        match.match_id,
        match,
      ]),
    ).values(),
  ];
  const asOf = oldestEvidenceTime(evidence);
  const totalRounds = seasonRounds(season, live.data?.total_matchweeks);
  const nextSaved = saved.some((item) => item.match_id === featured?.match_id);
  const error = live.error ?? fixtures.error;
  const loading = live.loading || fixtures.loading;
  return (
    <div className="matchday-page">
      <section className="hero hub-hero">
        <div className="hero-copy">
          <span className="eyebrow">PANBALL / MATCHDAY HUB</span>
          <h1>สรุปก่อนเชียร์</h1>
          <p>นัดถัดไป ฟอร์มล่าสุด และประเด็นที่ควรรู้</p>
          <span className="badge">กำลังดู {team.name}</span>
        </div>
      </section>
      <div className="status-strip">
        <span>
          ฤดูกาล {season ?? "—"} · อัปเดตล่าสุด{" "}
          {live.data?.last_ingest_at
            ? dateTime(live.data.last_ingest_at)
            : "ไม่ทราบเวลาอัปเดต"}
        </span>
        <button
          onClick={() => {
            setClock(Date.now());
            setRevision((x) => x + 1);
          }}
        >
          รีเฟรชข้อมูล
        </button>
      </div>
      <div
        className={`hub-grid prediction-hub ${next ? "has-next" : "no-next"}`}
      >
        {loading ? (
          <div className="panel hub-next">
            <Loading />
          </div>
        ) : error ? (
          <div className="panel hub-next">
            <ErrorBox error={error} retry={() => setRevision((x) => x + 1)} />
          </div>
        ) : season ? (
          <section className="panel hub-next">
            <header className="panel-heading">
              <h2>
                <CalendarDays size={20} />{" "}
                {featured?.status === "LIVE"
                  ? "กำลังแข่งขัน"
                  : featured?.status === "FINISHED"
                    ? "ผลล่าสุดของทีม"
                    : "นัดถัดไป"}
              </h2>
              {featured && (
                <span className="muted">
                  นัดที่ {featured.matchweek}
                  {totalRounds ? ` จาก ${totalRounds} นัด` : ""}
                </span>
              )}
            </header>
            {featured ? (
              <>
                <div className="hub-match">
                  <div>
                    <TeamCrest
                      id={featured.home.team_id}
                      name={featured.home.name}
                      size={72}
                    />
                    <h3>{featured.home.name}</h3>
                  </div>
                  <div>
                    <time dateTime={featured.kickoff} className="next-kickoff">
                      <span>
                        {new Date(featured.kickoff).toLocaleDateString(
                          "th-TH",
                          {
                            timeZone: "Asia/Bangkok",
                            weekday: "short",
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                          },
                        )}
                      </span>
                      <b>
                        {new Date(featured.kickoff).toLocaleTimeString(
                          "th-TH",
                          {
                            timeZone: "Asia/Bangkok",
                            hour: "2-digit",
                            minute: "2-digit",
                          },
                        )}
                      </b>
                    </time>
                    <strong className="hub-vs">
                      {featured.status === "SCHEDULED"
                        ? "VS"
                        : `${featured.score.home ?? "—"} : ${featured.score.away ?? "—"}`}
                    </strong>
                    {featured.venue?.name && (
                      <small>{featured.venue.name}</small>
                    )}
                  </div>
                  <div>
                    <TeamCrest
                      id={featured.away.team_id}
                      name={featured.away.name}
                      size={72}
                    />
                    <h3>{featured.away.name}</h3>
                  </div>
                </div>
                <Prediction match={featured} revision={revision} />
                <div className="hub-actions">
                  <Link
                    className="button primary"
                    href={`/matches/${featured.match_id}`}
                  >
                    ดูรายละเอียดแมตช์ <ArrowUpRight size={18} />
                  </Link>
                  {featured.status === "SCHEDULED" && (
                    <button
                      disabled={!ready}
                      aria-pressed={nextSaved}
                      onClick={() =>
                        toggle({
                          match_id: featured.match_id,
                          season: featured.season,
                        })
                      }
                    >
                      <Bookmark size={18} />
                      {nextSaved ? "บันทึกแล้ว" : "บันทึกแมตช์"}
                    </button>
                  )}
                </div>
              </>
            ) : (
              <p className="empty">
                ยังไม่มีโปรแกรมนัดถัดไปของ {team.shortName} ในระบบ
              </p>
            )}
          </section>
        ) : (
          <p className="panel hub-next empty">
            ยังไม่มีข้อมูลฤดูกาล กรุณาลองใหม่ภายหลัง
          </p>
        )}
        {!loading && !error && next && (
          <section className="panel hub-form">
            <h2>
              <BarChart3 size={22} />
              เทียบฟอร์มก่อนเกม
            </h2>
            <p className="muted">
              สูงสุด 5 นัดที่มีข้อมูลในฤดูกาลนี้ · เก่า → ล่าสุด
            </p>
            <div className="form-comparison">
              <div>
                <TeamName id={team.teamId} name={team.shortName} />
                <FormBadges results={first.results} />
                <small>พบข้อมูล {first.count} นัด</small>
              </div>
              {opponent && second ? (
                <div>
                  <TeamName id={opponent.team_id} name={opponent.name} />
                  <FormBadges results={second.results} />
                  <small>พบข้อมูล {second.count} นัด</small>
                </div>
              ) : (
                <p className="muted">รอข้อมูลคู่แข่งนัดถัดไป</p>
              )}
            </div>
            <table className="comparison-table">
              <caption className="sr-only">
                เปรียบเทียบสถิติจากนัดที่มีข้อมูล
              </caption>
              <thead>
                <tr>
                  <th>{team.shortName}</th>
                  <th>สถิติ</th>
                  <th>{opponent?.name ?? "คู่แข่ง"}</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["won", "ชนะ"],
                    ["draw", "เสมอ"],
                    ["lost", "แพ้"],
                    ["goalsFor", "ยิงได้"],
                    ["goalsAgainst", "เสีย"],
                  ] as const
                ).map(([key, label]) => (
                  <tr key={key}>
                    <td>{first.count ? first[key] : "—"}</td>
                    <th scope="row">{label}</th>
                    <td>{second?.count ? second[key] : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="form-legend">
              ✓ ชนะ · − เสมอ · × แพ้ · วงแหวน = นัดล่าสุด
            </p>
          </section>
        )}
        <SeasonOutlook teamId={team.teamId} revision={revision} />
        <section className="panel hub-saved">
          <h2>
            <Bookmark size={20} /> แมตช์ที่บันทึกไว้
          </h2>
          <p className="muted">บันทึกในเบราว์เซอร์นี้ · เฉพาะบัญชีของคุณ</p>
          {storageError && <p role="alert">{storageError}</p>}
          {!saved.length && (
            <p className="empty">
              กด “บันทึกแมตช์” ที่นัดถัดไปเพื่อเก็บไว้ดูภายหลัง
            </p>
          )}
          <SavedMatches
            saved={saved}
            remove={toggle}
            now={clock}
            revision={revision}
          />
        </section>
        {!loading && !error && next && (
          <section className="panel hub-brief">
            <h2>
              <FileText size={22} />
              ประเด็นก่อนเกม
            </h2>
            {first.count ? (
              <ol className="brief-list">
                <li>
                  <TeamCrest id={team.teamId} name={team.name} size={38} />
                  <strong>
                    {team.shortName} ชนะ {first.won} จาก {first.count}{" "}
                    นัดที่มีข้อมูล
                  </strong>
                  <span>รวมเฉพาะเกมจบแล้วก่อนเวลาที่ใช้สรุป</span>
                </li>
                <li>
                  <TeamCrest id={team.teamId} name={team.name} size={38} />
                  <strong>
                    {team.shortName} ยิงได้ {first.goalsFor} และเสีย{" "}
                    {first.goalsAgainst} ประตู
                  </strong>
                  <span>คำนวณจากชุดการแข่งขันเดียวกับฟอร์มด้านบน</span>
                </li>
                {second && opponent && second.count > 0 && (
                  <li>
                    <TeamCrest
                      id={opponent.team_id}
                      name={opponent.name}
                      size={38}
                    />
                    <strong>
                      {opponent.name} ชนะ {second.won} จาก {second.count}{" "}
                      นัดที่มีข้อมูล
                    </strong>
                    <span>
                      ยิงได้ {second.goalsFor} · เสีย {second.goalsAgainst}{" "}
                      ประตู
                    </span>
                  </li>
                )}
              </ol>
            ) : (
              <p className="empty">
                ยังมีข้อมูลผลการแข่งขันไม่เพียงพอสำหรับสรุป
              </p>
            )}
            <p className="muted">
              เวลาข้อมูลเก่าสุดที่ใช้:{" "}
              {asOf ? dateTime(asOf) : "ไม่ทราบเวลาอัปเดต"}
            </p>
            <Link
              className="text-link"
              href={`/football/fixtures?team_id=${team.teamId}`}
            >
              ดูโปรแกรมและข้อมูลอ้างอิง →
            </Link>
            {evidence.length > 0 && (
              <details className="hub-evidence">
                <summary>ดูข้อมูลอ้างอิง ({evidence.length} นัด)</summary>
                {evidence.map((match) => (
                  <Link
                    key={match.match_id}
                    href={`/matches/${match.match_id}`}
                  >
                    {match.home.name} {match.score.home} : {match.score.away}{" "}
                    {match.away.name}
                    <small>
                      {dateTime(match.kickoff)} · ข้อมูล ณ{" "}
                      {match.fetched_at
                        ? dateTime(match.fetched_at)
                        : "ไม่ทราบ"}
                    </small>
                  </Link>
                ))}
              </details>
            )}
          </section>
        )}
        {!loading && !error && (
          <section className="panel hub-latest">
            <h2>
              <Trophy size={20} />
              ผลล่าสุดของ {team.shortName}
            </h2>
            {latest ? (
              <Link
                className="latest-result"
                href={`/matches/${latest.match_id}`}
              >
                <TeamName id={latest.home.team_id} name={latest.home.name} />
                <strong>
                  {latest.score.home} : {latest.score.away}
                </strong>
                <TeamName id={latest.away.team_id} name={latest.away.name} />
                <small>
                  {dateTime(latest.kickoff)} · พรีเมียร์ลีก นัดที่{" "}
                  {latest.matchweek} · จบการแข่งขัน
                </small>
              </Link>
            ) : (
              <p className="empty">ยังไม่มีผลการแข่งขันที่พร้อมแสดง</p>
            )}
            <Link
              className="text-link"
              href={`/football/fixtures?team_id=${team.teamId}&status=FINISHED`}
            >
              ดูผลทั้งหมด →
            </Link>
            <button
              onClick={() => app.ask(`สรุปผลการแข่งขันล่าสุดของ ${team.name}`)}
            >
              <MessageCircle size={18} /> ถามแพนด้าเกี่ยวกับ {team.shortName}
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
