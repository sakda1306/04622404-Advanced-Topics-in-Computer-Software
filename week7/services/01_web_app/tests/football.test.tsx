import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import FootballPage from "../app/football/[view]/page";
import MatchPage from "../app/matches/[id]/page";
vi.mock("../components/AppProvider", () => ({
  useApp: () => ({ browsingTeam: { teamId: 66 } }),
}));
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status });
it("treats an unpublished/missing report as an empty state", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) =>
      path === "/api/football/status"
        ? json({ current_season: "2026", current_matchweek: 6, quota: {} })
        : json({ code: "NOT_FOUND", detail: "missing" }, 404),
    ),
  );
  render(<FootballPage params={{ view: "reports" }} />);
  expect(
    await screen.findByText("ยังไม่มีรายงานที่เผยแพร่ในช่วงที่เลือก"),
  ).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("treats a season without standings as an empty state", async () => {
  // The standings page also asks for finished fixtures (team form) once the season is known: answer
  // that one like the real API does, or its error box races with the assertion below.
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) =>
      path === "/api/football/status"
        ? json({ current_season: "2026", current_matchweek: 6, quota: {} })
        : path.startsWith("/api/football/fixtures")
          ? json({ matches: [] })
          : json({ code: "NOT_FOUND", detail: "missing" }, 404),
    ),
  );
  render(<FootballPage params={{ view: "standings" }} />);
  expect(
    await screen.findByText("ยังไม่มีตารางคะแนนของฤดูกาลนี้"),
  ).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("uses API supported fixture query filters", async () => {
  const fetcher = vi.fn(async (path: string) =>
    path === "/api/football/status"
      ? json({ current_season: "2026", current_matchweek: 6, quota: {} })
      : json({ matches: [] }),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<FootballPage params={{ view: "fixtures" }} />);
  await userEvent.selectOptions(screen.getByLabelText("ทีม"), "64");
  await userEvent.selectOptions(screen.getByLabelText("สถานะ"), "FINISHED");
  await userEvent.click(screen.getByRole("button", { name: "แสดงข้อมูล" }));
  await screen.findByText("ไม่มีการแข่งขันตรงกับตัวกรอง");
  expect(
    fetcher.mock.calls.some(
      ([path]) =>
        path.includes("team_id=64") && path.includes("status=FINISHED"),
    ),
  ).toBe(true);
});
it("handles null match detail without crashing", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      json({
        match_id: "m1",
        home: { name: "Arsenal" },
        away: { name: "Chelsea" },
        score: { home: 2, away: 1 },
        kickoff: "2026-09-20T18:30:00+07:00",
        matchweek: 5,
        events: null,
        lineups: null,
        statistics: null,
      }),
    ),
  );
  render(<MatchPage params={{ id: "m1" }} />);
  expect(
    await screen.findByText("ยังไม่มีข้อมูลเหตุการณ์"),
  ).toBeInTheDocument();
  expect(screen.getAllByText("ยังไม่มีข้อมูลส่วนนี้")).toHaveLength(2);
});

it.each(["57", "all"])(
  "preserves linked fixture filters for team %s on first load",
  async (team) => {
    const fetcher = vi.fn(async (path: string) =>
      path === "/api/football/status"
        ? json({ current_season: "2026", current_matchweek: 6, quota: {} })
        : json({ matches: [] }),
    );
    vi.stubGlobal("fetch", fetcher);
    render(
      <FootballPage
        params={{ view: "fixtures" }}
        searchParams={{
          team_id: team,
          status: "FINISHED",
          matchweek: "4",
          season: "2026",
        }}
      />,
    );
    await screen.findByText("ไม่มีการแข่งขันตรงกับตัวกรอง");
    const calls = fetcher.mock.calls.filter(([path]) =>
      path.includes("/fixtures"),
    );
    expect(calls.length).toBeGreaterThan(0);
    for (const [path] of calls) {
      const params = new URL(path, "http://localhost").searchParams;
      expect(params.get("team_id")).toBe(team === "all" ? null : team);
      expect(params.get("status")).toBe("FINISHED");
      expect(params.get("matchweek")).toBe("4");
    }
  },
);
