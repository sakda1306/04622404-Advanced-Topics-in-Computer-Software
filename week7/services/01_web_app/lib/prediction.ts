export type MatchPrediction = {
  data: {
    home_win: number;
    draw: number;
    away_win: number;
    home_xg: number;
    away_xg: number;
    most_likely_score: { home: number; away: number };
    method: string;
    matches_used: number;
    as_of: string | null;
  };
};
export type SimulationTeam = {
  team_id: number;
  name: string;
  short_name: string;
  points: number;
  expected_points: number;
  p_title: number;
  p_top4: number;
  p_relegation: number;
  position_probs: number[];
};
export type SimulationSnapshot = {
  season: string;
  as_of: string | null;
  computed_at: string;
  stale: boolean;
  n_sims: number;
  model: string;
  teams: SimulationTeam[];
};
export const predictionNotice =
  "ประมาณการจากแบบจำลองสถิติ ไม่ใช่คำแนะนำการพนัน";
export function probability(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 1
  );
}
export function percent(value: number) {
  if (!probability(value)) return "—";
  return value > 0 && Math.round(value * 100) === 0
    ? "<1%"
    : `${Math.round(value * 100)}%`;
}
const nonnegative = (x: unknown): x is number =>
  typeof x === "number" && Number.isFinite(x) && x >= 0;
export function validPrediction(value: MatchPrediction) {
  const d = value?.data;
  return (
    !!d &&
    [d.home_win, d.draw, d.away_win].every(probability) &&
    Math.abs(d.home_win + d.draw + d.away_win - 1) < 0.02 &&
    [
      d.home_xg,
      d.away_xg,
      d.most_likely_score?.home,
      d.most_likely_score?.away,
    ].every(nonnegative)
  );
}
export function validSimulation(value: SimulationSnapshot) {
  return (
    !!value &&
    typeof value.season === "string" &&
    typeof value.stale === "boolean" &&
    Number.isInteger(value.n_sims) &&
    value.n_sims > 0 &&
    Array.isArray(value.teams) &&
    new Set(value.teams.map((t) => t?.team_id)).size === value.teams.length &&
    value.teams.every(
      (t) =>
        t &&
        Number.isInteger(t.team_id) &&
        t.team_id > 0 &&
        typeof t.name === "string" &&
        typeof t.short_name === "string" &&
        [t.points, t.expected_points].every(nonnegative) &&
        [t.p_title, t.p_top4, t.p_relegation].every(probability) &&
        Array.isArray(t.position_probs) &&
        t.position_probs.length === value.teams.length &&
        t.position_probs.every(probability) &&
        Math.abs(t.position_probs.reduce((a, b) => a + b, 0) - 1) < 0.02,
    )
  );
}
