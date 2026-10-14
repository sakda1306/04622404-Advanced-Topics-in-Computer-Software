import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi, afterEach } from "vitest";
import { MatchdayHub } from "../components/MatchdayHub";
import { seasonRounds } from "../lib/competition";
const state = vi.hoisted(() => ({
  user: { id: "A" },
  browsingTeam: { teamId: 57, name: "Arsenal", shortName: "Arsenal" },
  ask: vi.fn(),
}));
vi.mock("../components/AppProvider", () => ({ useApp: () => state }));
const fixture = {
  match_id: "next-match",
  season: "2026",
  matchweek: 6,
  kickoff: "2099-10-01T12:00:00Z",
  status: "SCHEDULED",
  home: { team_id: 57, name: "Arsenal" },
  away: { team_id: 61, name: "Chelsea" },
  score: { home: null, away: null },
};
afterEach(() => {
  localStorage.clear();
  state.user = { id: "A" };
});
it("renders fixtures without AI calls, saves locally, and isolates bookmarks on account switch", async () => {
  const fetcher = vi.fn(
    async (path: string) =>
      new Response(
        JSON.stringify(
          path.includes("/status")
            ? { current_season: "2026" }
            : path.includes("/standings")
              ? { rows: [] }
              : path.includes("/matches/")
                ? fixture
                : { matches: [fixture] },
        ),
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  const view = render(<MatchdayHub />);
  const save = await screen.findByRole("button", { name: "บันทึกแมตช์" });
  await userEvent.click(save);
  expect(screen.getByRole("button", { name: "บันทึกแล้ว" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(JSON.parse(localStorage.getItem("panball:saved:v1:A")!)).toEqual([
    { match_id: "next-match", season: "2026" },
  ]);
  expect(screen.getByText("นัดที่ 6 จาก 38 นัด")).toBeInTheDocument();
  expect(
    fetcher.mock.calls.every(([path]) => path.startsWith("/api/football/")),
  ).toBe(true);
  state.user = { id: "B" };
  view.rerender(<MatchdayHub />);
  await screen.findByRole("button", { name: "บันทึกแมตช์" });
  expect(
    screen.queryByRole("button", { name: "ลบแมตช์ที่บันทึก" }),
  ).not.toBeInTheDocument();
});
it("states empty coverage and does not show invented zero stats", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (path: string) =>
        new Response(
          JSON.stringify(
            path.includes("/status")
              ? { current_season: "2026" }
              : { matches: [], rows: [] },
          ),
        ),
    ),
  );
  render(<MatchdayHub />);
  expect(
    await screen.findByText("ยังไม่มีโปรแกรมนัดถัดไปของ Arsenal ในระบบ"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "เทียบฟอร์มก่อนเกม" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "ประเด็นก่อนเกม" }),
  ).not.toBeInTheDocument();
});
it("only falls back to verified season round counts", () => {
  expect(seasonRounds("2026")).toBe(38);
  expect(seasonRounds("1900")).toBeUndefined();
  expect(seasonRounds("1900", 42)).toBe(42);
});

it.each([true, false])(
  "prioritizes live then latest result when no future fixture (live=%s)",
  async (isLive) => {
    const completed = {
      ...fixture,
      match_id: "finished",
      kickoff: "2026-01-01T12:00:00Z",
      status: "FINISHED",
      score: { home: 2, away: 1 },
    };
    const inProgress = {
      ...completed,
      match_id: "live",
      status: "LIVE",
      score: { home: 1, away: 0 },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (path: string) =>
          new Response(
            JSON.stringify(
              path.includes("/status")
                ? { current_season: "2026" }
                : {
                    matches: isLive
                      ? [completed, fixture, inProgress]
                      : [completed],
                  },
            ),
          ),
      ),
    );
    render(<MatchdayHub />);
    await screen.findByRole("heading", {
      name: isLive ? "กำลังแข่งขัน" : "ผลล่าสุดของทีม",
    });
    expect(
      screen.getByRole("link", { name: "ดูรายละเอียดแมตช์" }),
    ).toHaveAttribute("href", `/matches/${isLive ? "live" : "finished"}`);
    expect(
      screen.queryByRole("region", { name: "โอกาสจากแบบจำลอง" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "บันทึกแมตช์" }),
    ).not.toBeInTheDocument();
  },
);

it("keeps saved matches and season outlook reachable when fixtures fail", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) =>
      path.includes("/status")
        ? new Response(JSON.stringify({ current_season: "2026" }))
        : new Response(JSON.stringify({ detail: "unavailable" }), {
            status: 503,
          }),
    ),
  );
  render(<MatchdayHub />);
  await waitFor(() =>
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0),
  );
  expect(
    screen.getByRole("heading", { name: "แมตช์ที่บันทึกไว้" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "โอกาสทั้งฤดูกาล" }),
  ).toBeInTheDocument();
});
