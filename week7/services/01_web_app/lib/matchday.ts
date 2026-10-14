import { Match } from "./types";
export type Outcome = "W" | "D" | "L";
export function clubMatches(matches: Match[], teamId: number) {
  const unique = new Map<string, Match>();
  for (const match of matches)
    if (
      (match.home.team_id === teamId || match.away.team_id === teamId) &&
      Number.isFinite(Date.parse(match.kickoff))
    )
      unique.set(match.match_id, match);
  return [...unique.values()].sort(
    (a, b) => Date.parse(a.kickoff) - Date.parse(b.kickoff),
  );
}
export function nextMatch(matches: Match[], teamId: number, now = Date.now()) {
  return clubMatches(matches, teamId).find(
    (match) => match.status === "SCHEDULED" && Date.parse(match.kickoff) >= now,
  );
}
export function recentForm(
  matches: Match[],
  teamId: number,
  cutoff = Date.now(),
) {
  const games = clubMatches(matches, teamId)
    .filter(
      (match) =>
        match.status === "FINISHED" &&
        Date.parse(match.kickoff) < cutoff &&
        typeof match.score.home === "number" &&
        Number.isFinite(match.score.home) &&
        match.score.home >= 0 &&
        typeof match.score.away === "number" &&
        Number.isFinite(match.score.away) &&
        match.score.away >= 0,
    )
    .slice(-5);
  const results: Outcome[] = [];
  let goalsFor = 0,
    goalsAgainst = 0;
  for (const match of games) {
    const home = match.home.team_id === teamId;
    const scored = (home ? match.score.home : match.score.away)!;
    const conceded = (home ? match.score.away : match.score.home)!;
    goalsFor += scored;
    goalsAgainst += conceded;
    results.push(scored > conceded ? "W" : scored < conceded ? "L" : "D");
  }
  return {
    games,
    results,
    count: games.length,
    won: results.filter((x) => x === "W").length,
    draw: results.filter((x) => x === "D").length,
    lost: results.filter((x) => x === "L").length,
    goalsFor,
    goalsAgainst,
  };
}
export function oldestEvidenceTime(matches: Match[]) {
  if (
    !matches.length ||
    matches.some(
      (match) =>
        !match.fetched_at || !Number.isFinite(Date.parse(match.fetched_at)),
    )
  )
    return null;
  return matches
    .map((match) => match.fetched_at!)
    .sort((a, b) => Date.parse(a) - Date.parse(b))[0];
}
export type SavedMatch = { match_id: string; season: string };
export function readSavedMatches(userId: string): SavedMatch[] {
  try {
    const parsed: unknown = JSON.parse(
      localStorage.getItem(`panball:saved:v1:${userId}`) ?? "[]",
    );
    if (!Array.isArray(parsed)) return [];
    const ids = new Set<string>();
    return parsed
      .filter((item): item is SavedMatch => {
        if (
          !item ||
          typeof item.match_id !== "string" ||
          !/^[A-Za-z0-9-]{1,64}$/.test(item.match_id) ||
          !/^\d{4}$/.test(item.season) ||
          ids.has(item.match_id)
        )
          return false;
        ids.add(item.match_id);
        return true;
      })
      .slice(0, 20);
  } catch {
    return [];
  }
}
