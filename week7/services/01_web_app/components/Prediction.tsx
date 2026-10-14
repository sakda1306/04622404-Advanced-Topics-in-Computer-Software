"use client";
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Match, dateTime } from "../lib/types";
import {
  MatchPrediction,
  percent,
  predictionNotice,
  validPrediction,
} from "../lib/prediction";
import { teamFromId } from "../lib/teams";
import { useRemote } from "../lib/use-remote";
import { ApiError } from "../lib/api";
import { ErrorBox, Loading } from "./Ui";

export function Prediction({
  match,
  revision = 0,
}: {
  match: Match;
  revision?: number;
}) {
  const [retry, setRetry] = useState(0);
  const result = useRemote<MatchPrediction>(
    match.status === "SCHEDULED"
      ? `/football/predict?home_team_id=${match.home.team_id}&away_team_id=${match.away.team_id}`
      : null,
    revision + retry,
  );
  if (match.status !== "SCHEDULED") return null;
  if (
    result.error instanceof ApiError &&
    [404, 422].includes(result.error.status)
  )
    return null;
  const invalid = result.data && !validPrediction(result.data);
  const error =
    result.error ||
    (invalid ? new Error("ข้อมูลทำนายยังไม่สมบูรณ์ กรุณาลองใหม่") : undefined);
  const d = !error && result.data?.data;
  return (
    <section className="prediction-strip" aria-label="โอกาสจากแบบจำลอง">
      <h3>
        <Sparkles size={17} /> โอกาสจากแบบจำลอง{" "}
        <span className="badge">PRE-MATCH</span>
      </h3>
      {result.loading ? (
        <Loading />
      ) : error ? (
        <ErrorBox
          error={
            new Error(
              result.error instanceof ApiError && result.error.status === 503
                ? "ระบบทำนายผลไม่พร้อมใช้งานตอนนี้"
                : error.message,
            )
          }
          retry={() => setRetry((x) => x + 1)}
        />
      ) : d ? (
        <>
          <div className="prediction-labels">
            <span>
              {match.home.name} ชนะ <b>{percent(d.home_win)}</b>
            </span>
            <span>
              เสมอ <b>{percent(d.draw)}</b>
            </span>
            <span>
              {match.away.name} ชนะ <b>{percent(d.away_win)}</b>
            </span>
          </div>
          <div className="prediction-track" aria-hidden="true">
            <i
              style={{
                flex: d.home_win,
                background:
                  teamFromId(match.home.team_id)?.colorBright ?? "#00b4ff",
              }}
            />
            <i style={{ flex: d.draw, background: "#8a98aa" }} />
            <i
              style={{
                flex: d.away_win,
                background:
                  teamFromId(match.away.team_id)?.colorBright ?? "#00b4ff",
              }}
            />
          </div>
          <div className="prediction-score">
            <span>
              สกอร์ที่น่าจะเป็นที่สุด{" "}
              <strong>
                {d.most_likely_score.home}–{d.most_likely_score.away}
              </strong>
            </span>
            <span>
              xG {d.home_xg.toFixed(2)} – {d.away_xg.toFixed(2)}
            </span>
          </div>
          <small className="muted">
            ข้อมูล ณ {d.as_of ? dateTime(d.as_of) : "ไม่ทราบเวลาอัปเดต"}
          </small>
          <p className="prediction-notice">{predictionNotice}</p>
        </>
      ) : null}
    </section>
  );
}
