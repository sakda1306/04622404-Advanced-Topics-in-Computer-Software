import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Prediction } from "../components/Prediction";
import { SeasonOutlook, SimulationPage } from "../components/Simulation";
import { Match } from "../lib/types";
import {
  percent,
  predictionNotice,
  validPrediction,
  validSimulation,
} from "../lib/prediction";
import { TraceView } from "../components/Answer";
import { SuggestedQuestions } from "../components/SuggestedQuestions";
import { SavedMatches } from "../components/SavedMatches";
const state = vi.hoisted(() => ({
  browsingTeam: { teamId: 57, name: "Arsenal", shortName: "Arsenal" },
  ask: vi.fn(),
}));
vi.mock("../components/AppProvider", () => ({ useApp: () => state }));
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });
const match: Match = {
  match_id: "future",
  season: "2026",
  matchweek: 6,
  kickoff: "2099-10-04T15:30:00Z",
  status: "SCHEDULED",
  home: { team_id: 57, name: "Arsenal" },
  away: { team_id: 61, name: "Chelsea" },
  score: { home: null, away: null },
};
const prediction = {
  data: {
    home_win: 0.48,
    draw: 0.26,
    away_win: 0.26,
    home_xg: 1.62,
    away_xg: 1.05,
    most_likely_score: { home: 1, away: 0 },
    as_of: null,
    method: "poisson-v1",
    matches_used: 43,
  },
};
const snapshot = {
  season: "2026",
  as_of: null,
  computed_at: "2026-10-01T00:00:00Z",
  stale: true,
  n_sims: 10000,
  model: "poisson-mc-v1",
  teams: Array.from({ length: 20 }, (_, i) => ({
    team_id: 57 + i,
    name: i === 0 ? "Arsenal FC" : `Club ${i}`,
    short_name: i === 0 ? "Arsenal" : `Club ${i}`,
    points: 13,
    expected_points: 74.3 - i,
    p_title: 0.31,
    p_top4: 0.82,
    p_relegation: 0.001,
    position_probs: Array.from({ length: 20 }, (_, rank) =>
      rank === i ? 1 : 0,
    ),
  })),
};
it("formats probabilities and rejects impossible or incomplete model values", () => {
  expect([0, 0.001, 0.26, 1, NaN].map(percent)).toEqual([
    "0%",
    "<1%",
    "26%",
    "100%",
    "—",
  ]);
  expect(validPrediction(prediction)).toBe(true);
  expect(validPrediction({ data: { ...prediction.data, home_win: 1.5 } })).toBe(
    false,
  );
  expect(validSimulation(snapshot)).toBe(true);
  expect(
    validSimulation({
      ...snapshot,
      teams: [{ ...snapshot.teams[0], position_probs: [] }],
    }),
  ).toBe(false);
});
it("shows backend probabilities, score and xG only for a scheduled match", async () => {
  const fetcher = vi.fn(async () => json(prediction));
  vi.stubGlobal("fetch", fetcher);
  const view = render(<Prediction match={match} />);
  expect(await screen.findByText("48%")).toBeInTheDocument();
  expect(screen.getByText("1–0")).toBeInTheDocument();
  expect(screen.getByText("xG 1.62 – 1.05")).toBeInTheDocument();
  expect(screen.getByText(predictionNotice)).toBeInTheDocument();
  view.rerender(<Prediction match={{ ...match, status: "LIVE" }} />);
  expect(screen.queryByLabelText("โอกาสจากแบบจำลอง")).not.toBeInTheDocument();
  view.rerender(<Prediction match={{ ...match, status: "FINISHED" }} />);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it.each([404, 422, 503])("handles prediction HTTP %s", async (status) => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      json({ code: "SIMULATION_UNAVAILABLE", detail: "unavailable" }, status),
    ),
  );
  render(<Prediction match={match} />);
  await waitFor(() =>
    expect(screen.queryByRole("status")).not.toBeInTheDocument(),
  );
  if (status === 503)
    expect(screen.getByRole("alert")).toHaveTextContent(
      "ระบบทำนายผลไม่พร้อมใช้งานตอนนี้",
    );
  else
    expect(screen.queryByLabelText("โอกาสจากแบบจำลอง")).not.toBeInTheDocument();
});
it("ignores late prediction results after switching teams", async () => {
  let resolveOld!: (r: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) =>
      path.includes("home_team_id=57")
        ? new Promise<Response>((r) => {
            resolveOld = r;
          })
        : Promise.resolve(
            json({
              data: {
                ...prediction.data,
                home_win: 0.6,
                draw: 0.2,
                away_win: 0.2,
              },
            }),
          ),
    ),
  );
  const view = render(<Prediction match={match} />);
  view.rerender(
    <Prediction
      match={{ ...match, home: { team_id: 65, name: "Man City" } }}
    />,
  );
  expect(await screen.findByText("60%")).toBeInTheDocument();
  await act(async () => resolveOld(json(prediction)));
  expect(screen.queryByText("48%")).not.toBeInTheDocument();
});
it("selects another season row without fetching again and exposes stale/keyboard chart", async () => {
  const fetcher = vi.fn(async () => json(snapshot));
  vi.stubGlobal("fetch", fetcher);
  const view = render(<SeasonOutlook teamId={57} />);
  expect(await screen.findByText("ผลเก่า")).toBeInTheDocument();
  expect(screen.getByText("<1%")).toBeInTheDocument();
  view.rerender(<SeasonOutlook teamId={58} />);
  expect(screen.getByText("Club 1")).toBeInTheDocument();
  const slider = screen.getByRole("slider");
  fireEvent.change(slider, { target: { value: "2" } });
  expect(slider).toHaveAttribute("aria-valuetext", "อันดับ 2: 100%");
  expect(fetcher).toHaveBeenCalledTimes(1);
  view.rerender(<SeasonOutlook teamId={999} />);
  expect(screen.queryByRole("heading")).not.toBeInTheDocument();
});
it("renders every simulation team, expands a row and handles a service failure", async () => {
  const fetcher = vi.fn(async () => json(snapshot));
  vi.stubGlobal("fetch", fetcher);
  render(<SimulationPage />);
  const table = await screen.findByRole("table");
  expect(within(table).getAllByRole("row")).toHaveLength(21);
  const expand = screen.getByRole("button", {
    name: "ดูอันดับที่คาดของ Arsenal",
  });
  await userEvent.click(expand);
  expect(expand).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("slider")).toBeInTheDocument();
  expect(screen.getByText(predictionNotice)).toBeInTheDocument();
  fetcher.mockImplementation(async () =>
    json({ code: "SIMULATION_UNAVAILABLE" }, 503),
  );
  await userEvent.click(screen.getByRole("button", { name: "รีเฟรชผลจำลอง" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "ผลจำลองยังไม่พร้อม",
  );
});
it("fills a suggested question for the browsed team without changing preferences", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => json({ matches: [match] })),
  );
  render(<SuggestedQuestions />);
  await userEvent.click(
    await screen.findByRole("button", {
      name: "Arsenal กับ Chelsea ใครจะชนะ?",
    }),
  );
  expect(state.ask).toHaveBeenCalledWith("Arsenal กับ Chelsea ใครจะชนะ?");
});
it("keeps condense diagnostics separate from fallback and supports legacy traces", () => {
  const view = render(
    <TraceView
      trace={{
        standalone_query: "ใครยิงให้ลิเวอร์พูล",
        condense: "applied",
        fallback: null,
      }}
    />,
  );
  expect(
    screen.getByText("คำถามที่ใช้ค้นหา: ใครยิงให้ลิเวอร์พูล"),
  ).toBeInTheDocument();
  expect(screen.getByText("ไม่มี")).toBeInTheDocument();
  view.rerender(<TraceView trace={{ intent: "match_result" }} />);
  expect(screen.queryByText(/คำถามที่ใช้ค้นหา/)).not.toBeInTheDocument();
});
it("previews only the nearest two upcoming saved games while retaining all management entries", async () => {
  const games = [
    { ...match, match_id: "late", kickoff: "2099-10-09T12:00:00Z" },
    { ...match, match_id: "early", kickoff: "2099-10-02T12:00:00Z" },
    {
      ...match,
      match_id: "done",
      status: "FINISHED",
      kickoff: "2020-01-01T00:00:00Z",
    },
    { ...match, match_id: "middle", kickoff: "2099-10-05T12:00:00Z" },
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) =>
      json(games.find((x) => path.endsWith(x.match_id))),
    ),
  );
  const view = render(
    <SavedMatches
      saved={games.map((g) => ({ match_id: g.match_id, season: g.season }))}
      remove={vi.fn()}
      now={Date.now()}
      revision={0}
    />,
  );
  await waitFor(() =>
    expect(screen.queryByRole("status")).not.toBeInTheDocument(),
  );
  const previews = Array.from(
    view.container.querySelectorAll(":scope > .saved-row a"),
  ).map((a) => a.getAttribute("href"));
  expect(previews).toEqual(["/matches/early", "/matches/middle"]);
  expect(view.container.querySelectorAll("details .saved-row")).toHaveLength(4);
});
