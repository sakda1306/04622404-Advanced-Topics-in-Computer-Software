"use client";
import { Fragment, useId, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChartColumn, ChevronDown, Trophy } from "lucide-react";
import { useRemote } from "../lib/use-remote";
import { useApp } from "./AppProvider";
import { dateTime } from "../lib/types";
import {
  SimulationSnapshot,
  percent,
  predictionNotice,
  validSimulation,
} from "../lib/prediction";
import { ApiError } from "../lib/api";
import { TeamName } from "./FootballIdentity";
import { ErrorBox, Loading } from "./Ui";

export function PositionChart({
  values,
  name,
}: {
  values: number[];
  name: string;
}) {
  const [position, setPosition] = useState(1);
  const id = useId();
  const max = Math.max(...values, 0.01);
  return (
    <div className="position-chart">
      <div className="position-chart-heading">
        <label htmlFor={id}>อันดับที่คาด · {name}</label>
        <output htmlFor={id}>
          อันดับ {position}: {percent(values[position - 1])}
        </output>
      </div>
      <div className="position-bars" aria-hidden="true">
        {values.map((value, i) => (
          <div
            key={i}
            title={`อันดับ ${i + 1}: ${percent(value)}`}
            onMouseEnter={() => setPosition(i + 1)}
            className={position === i + 1 ? "selected" : ""}
          >
            <i style={{ height: `${Math.max(2, (value / max) * 100)}%` }} />
          </div>
        ))}
      </div>
      <input
        id={id}
        type="range"
        min={1}
        max={values.length}
        value={position}
        onChange={(e) => setPosition(Number(e.target.value))}
        aria-valuetext={`อันดับ ${position}: ${percent(values[position - 1])}`}
      />
      <div className="position-scale">
        <span>อันดับ 1</span>
        <small>เลื่อนเพื่อดูโอกาสแต่ละอันดับ</small>
        <span>{values.length}</span>
      </div>
    </div>
  );
}
function Chance({ label, value }: { label: string; value: number }) {
  return (
    <div className="chance">
      <span>{label}</span>
      <div aria-hidden="true">
        <i style={{ width: `${value * 100}%` }} />
      </div>
      <strong>{percent(value)}</strong>
    </div>
  );
}
function SnapshotMeta({ data }: { data: SimulationSnapshot }) {
  return (
    <div className="snapshot-meta">
      <span>จำลอง {data.n_sims.toLocaleString("th-TH")} ครั้ง</span>
      <span>
        ข้อมูล ณ {data.as_of ? dateTime(data.as_of) : "ไม่ทราบเวลาอัปเดต"}
      </span>
      {data.stale && <strong className="stale-badge">ผลเก่า</strong>}
    </div>
  );
}
function simulationError(error?: Error) {
  return error instanceof ApiError && error.status === 503
    ? new Error("ผลจำลองยังไม่พร้อม ลองใหม่ภายหลัง")
    : error;
}
function useSimulation(revision: number) {
  const resource = useRemote<SimulationSnapshot>(
    "/football/simulation",
    revision,
  );
  const valid = resource.data && validSimulation(resource.data);
  return {
    ...resource,
    data: valid ? resource.data : undefined,
    error:
      simulationError(resource.error) ??
      (resource.data && !valid
        ? new Error("ข้อมูลผลจำลองยังไม่สมบูรณ์ กรุณาลองใหม่")
        : undefined),
  };
}
export function SeasonOutlook({
  teamId,
  revision = 0,
}: {
  teamId: number;
  revision?: number;
}) {
  const [retry, setRetry] = useState(0);
  const resource = useSimulation(revision + retry);
  const team = resource.data?.teams.find((t) => t.team_id === teamId);
  if (resource.data && !team) return null;
  return (
    <section className="panel hub-season">
      <header className="panel-heading">
        <h2>
          <ChartColumn size={22} /> โอกาสทั้งฤดูกาล
        </h2>
        <span className="badge">SEASON OUTLOOK</span>
      </header>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorBox error={resource.error} retry={() => setRetry((x) => x + 1)} />
      ) : team && resource.data ? (
        <>
          <TeamName id={team.team_id} name={team.short_name || team.name} />
          <div className="points-outlook">
            <span>
              แต้มตอนนี้<strong>{team.points}</strong>
            </span>
            <ArrowRight aria-hidden="true" />
            <span>
              แต้มคาดเมื่อจบฤดูกาล
              <strong>{Math.round(team.expected_points)}</strong>
            </span>
          </div>
          <div className="season-chances">
            <Chance label="แชมป์" value={team.p_title} />
            <Chance label="ท็อป 4" value={team.p_top4} />
            <Chance label="ตกชั้น" value={team.p_relegation} />
          </div>
          <PositionChart
            key={team.team_id}
            values={team.position_probs}
            name={team.short_name}
          />
          <SnapshotMeta data={resource.data} />
          <p className="prediction-notice">{predictionNotice}</p>
        </>
      ) : null}
      <Link className="text-link simulation-link" href="/football/simulation">
        ดูผลจำลองทั้งลีก <ArrowRight size={16} />
      </Link>
    </section>
  );
}
export function SimulationPage() {
  const app = useApp();
  const [revision, setRevision] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);
  const resource = useSimulation(revision);
  const snapshot = resource.data;
  const leader = snapshot?.teams[0];
  return (
    <div className="football-page football-simulation">
      <section className="hero simulation-hero">
        <div className="hero-copy">
          <span className="eyebrow">PANBALL / SEASON LAB</span>
          <h1>ผลจำลองฤดูกาล</h1>
          <p>มองโอกาสของทุกทีม จนถึงนัดสุดท้าย</p>
        </div>
        <ChartColumn size={64} aria-hidden="true" />
      </section>
      <div className="status-strip">
        <span>พรีเมียร์ลีก · {snapshot?.season ?? "ฤดูกาลปัจจุบัน"}</span>
        <button onClick={() => setRevision((x) => x + 1)}>รีเฟรชผลจำลอง</button>
      </div>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorBox
          error={resource.error}
          retry={() => setRevision((x) => x + 1)}
        />
      ) : snapshot ? (
        <>
          <div className="simulation-overview">
            <div className="panel">
              <span className="eyebrow">แบบจำลองฤดูกาล</span>
              <strong>
                {snapshot.n_sims.toLocaleString("th-TH")} <small>ครั้ง</small>
              </strong>
              <p>จำลองการแข่งขันที่เหลือจากข้อมูลในระบบ</p>
            </div>
            <div className="panel">
              <span className="eyebrow">แต้มคาดการณ์สูงสุด</span>
              {leader ? (
                <>
                  <TeamName
                    id={leader.team_id}
                    name={leader.short_name || leader.name}
                  />
                  <strong>
                    {Math.round(leader.expected_points)} <small>แต้ม</small>
                  </strong>
                </>
              ) : (
                <p>ยังไม่มีทีมในผลจำลอง</p>
              )}
            </div>
            <div className="panel">
              <span className="eyebrow">สถานะข้อมูล</span>
              <SnapshotMeta data={snapshot} />
              <small className="muted">
                คำนวณเมื่อ {dateTime(snapshot.computed_at)}
              </small>
            </div>
          </div>
          <section className="panel simulation-results">
            <header className="panel-heading">
              <h2>
                <Trophy size={22} /> ภาพรวมทั้งลีก
              </h2>
              <small>เรียงตามแต้มคาดการณ์ · {snapshot.teams.length} ทีม</small>
            </header>
            {!snapshot.teams.length ? (
              <p className="empty">ยังไม่มีทีมในผลจำลอง</p>
            ) : (
              <table className="simulation-table">
                <caption className="sr-only">
                  โอกาสจบฤดูกาลของแต่ละทีม กดรายละเอียดเพื่อดูโอกาสแต่ละอันดับ
                </caption>
                <thead>
                  <tr>
                    <th># / ทีม</th>
                    <th>แต้มตอนนี้</th>
                    <th>แต้มที่คาด</th>
                    <th>แชมป์</th>
                    <th>ท็อป 4</th>
                    <th>ตกชั้น</th>
                    <th>รายละเอียด</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.teams.map((team, index) => (
                    <Fragment key={team.team_id}>
                      <tr
                        className={
                          team.team_id === app.browsingTeam.teamId
                            ? "club-row"
                            : ""
                        }
                      >
                        <th scope="row">
                          <span className="simulation-rank">{index + 1}</span>
                          <TeamName
                            id={team.team_id}
                            name={team.short_name || team.name}
                          />
                        </th>
                        <td>
                          <span className="mobile-cell-label">แต้มตอนนี้</span>
                          {team.points}
                        </td>
                        <td>
                          <span className="mobile-cell-label">แต้มที่คาด</span>
                          <strong>{Math.round(team.expected_points)}</strong>
                        </td>
                        <td>
                          <Chance label="แชมป์" value={team.p_title} />
                        </td>
                        <td>
                          <Chance label="ท็อป 4" value={team.p_top4} />
                        </td>
                        <td>
                          <Chance label="ตกชั้น" value={team.p_relegation} />
                        </td>
                        <td>
                          <button
                            className="simulation-expand"
                            aria-label={`ดูอันดับที่คาดของ ${team.short_name || team.name}`}
                            aria-expanded={expanded === team.team_id}
                            aria-controls={`position-${team.team_id}`}
                            onClick={() =>
                              setExpanded(
                                expanded === team.team_id ? null : team.team_id,
                              )
                            }
                          >
                            ดูอันดับ <ChevronDown size={16} />
                          </button>
                        </td>
                      </tr>
                      {expanded === team.team_id && (
                        <tr className="simulation-detail">
                          <td colSpan={7} id={`position-${team.team_id}`}>
                            <PositionChart
                              values={team.position_probs}
                              name={team.short_name || team.name}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            )}
            <p className="prediction-notice">{predictionNotice}</p>
          </section>
        </>
      ) : null}
    </div>
  );
}
