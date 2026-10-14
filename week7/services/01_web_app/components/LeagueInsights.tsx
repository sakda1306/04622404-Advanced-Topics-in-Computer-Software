"use client";
import { Trophy, Sparkles, ArrowRight } from "lucide-react";
import { Match, Standing } from "../lib/types";
import { recentForm } from "../lib/matchday";
import { TeamName, FormBadges } from "./FootballIdentity";

export function LeagueInsights({
  rows,
  matches,
  teamId,
}: {
  rows: Standing[];
  matches: Match[];
  teamId: number;
}) {
  const selected = rows.find((row) => row.team_id === teamId);
  const form = recentForm(matches, teamId);
  return (
    <aside className="league-insights" aria-label="ภาพรวมลีก">
      <section className="panel league-overview">
        <h2>
          <Trophy size={23} />
          ภาพรวมลีก
        </h2>
        <h3>5 อันดับแรก</h3>
        <table>
          <caption className="sr-only">5 อันดับแรกของลีก</caption>
          <thead>
            <tr>
              <th>#</th>
              <th>ทีม</th>
              <th>แข่ง</th>
              <th>+/−</th>
              <th>คะแนน</th>
            </tr>
          </thead>
          <tbody>
            {[...rows]
              .sort((a, b) => a.position - b.position)
              .slice(0, 5)
              .map((row) => (
                <tr
                  key={row.team_id}
                  className={row.team_id === teamId ? "club-row" : ""}
                >
                  <td>{row.position}</td>
                  <th scope="row">
                    <TeamName id={row.team_id} name={row.name} />
                  </th>
                  <td>{row.played}</td>
                  <td>{row.goal_difference}</td>
                  <td>
                    <strong>{row.points}</strong>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </section>
      <section className="panel league-form-guide">
        <h2>
          <Sparkles size={23} />
          ฟอร์ม 5 นัดล่าสุด
        </h2>
        {selected && (
          <p className="selected-form-team">
            <TeamName id={selected.team_id} name={selected.name} />
          </p>
        )}
        <div className="large-form">
          <FormBadges
            results={form.results}
            games={form.games}
            teamId={teamId}
          />
        </div>
        <div className="form-direction">
          <span>เก่าสุด</span>
          <ArrowRight size={22} />
          <span>ล่าสุด</span>
        </div>
        <div className="form-key">
          <span>
            <i className="form-dot W">✓</i>ชนะ
          </span>
          <span>
            <i className="form-dot D">−</i>เสมอ
          </span>
          <span>
            <i className="form-dot L">×</i>แพ้
          </span>
        </div>
        <p className="muted">วงแหวน = นัดล่าสุด · พบข้อมูล {form.count} นัด</p>
        <p className="form-help">
          แตะหรือวางเมาส์ที่ผลการแข่งขันเพื่อดูสกอร์ และเปิดรายละเอียดแมตช์
        </p>
      </section>
      <div className="league-signoff">
        <span className="eyebrow">EVERY MATCH. EVERY MOMENT.</span>
        <p>ตามทุกนัดของทีมที่คุณรัก</p>
        <strong>PANBALL</strong>
      </div>
    </aside>
  );
}
