import { expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Match } from "../lib/types";
import {
  nextMatch,
  recentForm,
  oldestEvidenceTime,
  readSavedMatches,
} from "../lib/matchday";
import { FormBadges, TeamCrest } from "../components/FootballIdentity";
const game = (
  id: string,
  time: string,
  home = 57,
  away = 61,
  score: [number | null, number | null] = [2, 1],
  status = "FINISHED",
): Match => ({
  match_id: id,
  season: "2026",
  matchweek: 1,
  kickoff: time,
  status,
  home: { team_id: home, name: "Home" },
  away: { team_id: away, name: "Away" },
  score: { home: score[0], away: score[1] },
  fetched_at: "2026-09-28T12:00:00Z",
});
afterEach(() => localStorage.clear());
it("selects only future scheduled matches of the browsing team", () => {
  const rows = [
    game("past", "2026-08-01", 57, 61, [null, null], "SCHEDULED"),
    game("other", "2026-10-01", 65, 66, [null, null], "SCHEDULED"),
    game("late", "2026-12-01", 57, 61, [null, null], "SCHEDULED"),
    game("soon", "2026-10-02", 61, 57, [null, null], "SCHEDULED"),
    game("post", "2026-10-01", 57, 61, [null, null], "POSTPONED"),
  ];
  expect(nextMatch(rows, 57, Date.parse("2026-09-30"))?.match_id).toBe("soon");
});
it("uses kickoff, deduplicates, excludes null scores and applies home/away perspective and cutoff", () => {
  const old = game("old", "2026-01-01");
  const away = game("away", "2026-09-02", 61, 57, [3, 1]);
  const rows = [
    old,
    game("draw", "2026-09-01", 57, 61, [1, 1]),
    away,
    away,
    game("null", "2026-09-03", 57, 61, [null, 1]),
    game("future", "2026-11-01"),
    game("bad", "invalid"),
    game("post", "2026-09-04", 57, 61, [2, 0], "POSTPONED"),
    game("other", "2026-09-02", 65, 66),
  ];
  const value = recentForm(rows, 57, Date.parse("2026-10-01"));
  expect(value.results).toEqual(["W", "D", "L"]);
  expect(value.goalsFor).toBe(4);
  expect(value.goalsAgainst).toBe(5);
  expect(value.count).toBe(3);
});
it("takes last five completed games and never invents missing timestamps", () => {
  const rows = Array.from({ length: 7 }, (_, i) =>
    game(String(i), `2026-09-0${i + 1}`),
  );
  const result = recentForm(rows, 57, Date.parse("2026-10-01"));
  expect(result.games.map((m) => m.match_id)).toEqual([
    "2",
    "3",
    "4",
    "5",
    "6",
  ]);
  expect(oldestEvidenceTime(result.games)).toBe("2026-09-28T12:00:00Z");
  expect(oldestEvidenceTime([{ ...rows[0], fetched_at: null }])).toBeNull();
  expect(recentForm([], 57).count).toBe(0);
});
it("isolates saved matches per account and rejects malformed storage", () => {
  localStorage.setItem(
    "panball:saved:v1:A",
    JSON.stringify([
      { match_id: "m1", season: "2026" },
      { match_id: "m1", season: "2026" },
      { match_id: "../bad", season: "2026" },
    ]),
  );
  expect(readSavedMatches("A")).toEqual([{ match_id: "m1", season: "2026" }]);
  expect(readSavedMatches("B")).toEqual([]);
  localStorage.setItem("panball:saved:v1:A", "broken");
  expect(readSavedMatches("A")).toEqual([]);
});
it("announces each outcome and latest badge without relying on colors", () => {
  render(<FormBadges results={["W", "D", "L"]} />);
  expect(screen.getAllByRole("img")).toHaveLength(3);
  expect(
    screen.getByRole("img", { name: "แพ้ · นัดล่าสุด" }),
  ).toHaveTextContent("×");
});
it("recovers the crest on changing team after a failed image", () => {
  const { container, rerender } = render(<TeamCrest id={999} name="Missing" />);
  fireEvent.error(container.querySelector("img")!);
  expect(container.querySelector("img")).toBeNull();
  rerender(<TeamCrest id={57} name="Arsenal" />);
  expect(container.querySelector("img")).toHaveAttribute(
    "src",
    "/crests/57.png",
  );
});
