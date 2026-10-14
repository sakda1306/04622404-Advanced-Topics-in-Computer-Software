"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { SavedMatch } from "../lib/matchday";
import { Match, dateTime } from "../lib/types";
import { TeamName } from "./FootballIdentity";
import { Loading } from "./Ui";

export function SavedMatches({
  saved,
  remove,
  now,
  revision,
}: {
  saved: SavedMatch[];
  remove: (item: SavedMatch) => void;
  now: number;
  revision: number;
}) {
  const [results, setResults] = useState<Record<string, Match | null>>({});
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const ids = saved.map((x) => x.match_id).join(",");
  useEffect(() => {
    const controller = new AbortController();
    const keys = ids ? ids.split(",") : [];
    setLoading(!!keys.length);
    setResults({});
    void Promise.all(
      keys.map(async (id) => {
        try {
          return [
            id,
            await api<Match>(`/football/matches/${encodeURIComponent(id)}`, {
              signal: controller.signal,
            }),
          ] as const;
        } catch {
          return [id, null] as const;
        }
      }),
    ).then((rows) => {
      if (!controller.signal.aborted) {
        setResults(Object.fromEntries(rows));
        setLoading(false);
      }
    });
    return () => controller.abort();
  }, [ids, revision, retry]);
  if (!saved.length) return null;
  if (loading) return <Loading />;
  const upcoming = saved
    .filter((item) => {
      const m = results[item.match_id];
      return m?.status === "SCHEDULED" && Date.parse(m.kickoff) >= now;
    })
    .sort(
      (a, b) =>
        Date.parse(results[a.match_id]!.kickoff) -
        Date.parse(results[b.match_id]!.kickoff),
    );
  const row = (item: SavedMatch) => {
    const m = results[item.match_id];
    return (
      <div className="saved-row" key={item.match_id}>
        <div>
          {m ? (
            <Link href={`/matches/${item.match_id}`}>
              <TeamName id={m.home.team_id} name={m.home.name} />
              <span> vs </span>
              <TeamName id={m.away.team_id} name={m.away.name} />
              <small>
                {dateTime(m.kickoff)} ·{" "}
                {{
                  SCHEDULED: "รอแข่งขัน",
                  LIVE: "กำลังแข่งขัน",
                  FINISHED: "จบการแข่งขัน",
                  POSTPONED: "เลื่อนการแข่งขัน",
                  CANCELLED: "ยกเลิก",
                }[m.status] ?? m.status}
              </small>
            </Link>
          ) : (
            <span>โหลดแมตช์ {item.match_id} ไม่สำเร็จ</span>
          )}
        </div>
        <button aria-label="ลบแมตช์ที่บันทึก" onClick={() => remove(item)}>
          <Trash2 size={16} />
        </button>
      </div>
    );
  };
  return (
    <>
      {upcoming.slice(0, 2).map(row)}
      {!upcoming.length && (
        <p className="muted">ยังไม่มีนัดที่รอแข่งขันในรายการบันทึก</p>
      )}
      {saved.some((x) => !results[x.match_id]) && (
        <button onClick={() => setRetry((x) => x + 1)}>ลองโหลดแมตช์ใหม่</button>
      )}
      <details className="saved-all">
        <summary>จัดการรายการทั้งหมด ({saved.length})</summary>
        {saved.map(row)}
      </details>
      <Link className="text-link" href="/football/fixtures?team_id=all">
        ดูโปรแกรมทั้งหมด →
      </Link>
    </>
  );
}
