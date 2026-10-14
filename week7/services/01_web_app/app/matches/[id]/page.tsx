"use client";
import Link from "next/link";
import { useState } from "react";
import { useRemote } from "../../../lib/use-remote";
import { dateTime, Match } from "../../../lib/types";
import { ErrorBox, Empty, Loading, PageTitle } from "../../../components/Ui";
import { TeamName } from "../../../components/FootballIdentity";
function StructuredData({ value }: { value: unknown }) {
  if (value == null || (Array.isArray(value) && !value.length))
    return <Empty>ยังไม่มีข้อมูลส่วนนี้</Empty>;
  if (typeof value !== "object") return <span>{String(value)}</span>;
  return (
    <dl className="data-list">
      {Object.entries(value).map(([key, item]) => (
        <div key={key}>
          <dt>{/^\d+$/.test(key) ? Number(key) + 1 : key}</dt>
          <dd>
            <StructuredData value={item} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
export default function MatchPage({ params }: { params: { id: string } }) {
  const [revision, setRevision] = useState(0),
    resource = useRemote<Match>(
      "/football/matches/" + encodeURIComponent(params.id),
      revision,
    );
  const match = resource.data;
  return (
    <>
      <Link className="text-link" href="/football/fixtures">
        ← กลับโปรแกรมการแข่งขัน
      </Link>
      <PageTitle
        eyebrow="MATCH CENTRE"
        title={
          match
            ? match.home.name + " vs " + match.away.name
            : "รายละเอียดการแข่งขัน"
        }
      />
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorBox
          error={resource.error}
          retry={() => setRevision((value) => value + 1)}
        />
      ) : (
        match && (
          <>
            <section className="panel match-detail">
              <p>
                {dateTime(match.kickoff)} · นัดที่ {match.matchweek}
              </p>
              <div className="latest-result">
                <TeamName id={match.home.team_id} name={match.home.name} />
                <strong>
                  {match.score.home ?? "—"} : {match.score.away ?? "—"}
                </strong>
                <TeamName id={match.away.team_id} name={match.away.name} />
              </div>
              <small>ข้อมูล ณ {dateTime(match.fetched_at)}</small>
            </section>
            <section className="panel">
              <h2>เหตุการณ์</h2>
              {match.events?.length ? (
                <ol className="events">
                  {match.events.map((event, index) => (
                    <li key={index}>
                      <b>{event.minute}′</b>
                      <span>
                        {event.type} · {event.player ?? "—"}
                      </span>
                    </li>
                  ))}
                </ol>
              ) : (
                <Empty>ยังไม่มีข้อมูลเหตุการณ์</Empty>
              )}
            </section>
            <div className="dashboard-grid">
              <section className="panel">
                <h2>รายชื่อผู้เล่น</h2>
                <StructuredData value={match.lineups} />
              </section>
              <section className="panel">
                <h2>สถิติการแข่งขัน</h2>
                <StructuredData value={match.statistics} />
              </section>
            </div>
          </>
        )
      )}
    </>
  );
}
