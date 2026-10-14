import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { FixtureList } from "../components/FixtureList";
import { FormBadges } from "../components/FootballIdentity";
import { Match } from "../lib/types";

const match: Match = {
  match_id: "fixture-1",
  season: "2026",
  matchweek: 4,
  kickoff: "2026-09-12T18:30:00Z",
  status: "FINISHED",
  home: { team_id: 57, name: "Arsenal" },
  away: { team_id: 61, name: "Chelsea" },
  score: { home: 2, away: 1 },
};
it("groups fixtures by Thai date and keeps all-team action outside match links", async () => {
  const showAll = vi.fn();
  render(
    <FixtureList
      matches={[
        match,
        { ...match, match_id: "fixture-2", kickoff: "2026-09-13T08:00:00Z" },
      ]}
      showAll={showAll}
    />,
  );
  expect(
    screen.getAllByRole("heading", { name: /13 กันยายน 2569/ }),
  ).toHaveLength(1);
  expect(screen.getByText("01:30")).toBeInTheDocument();
  expect(screen.queryByText(/Stadium/)).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "ดูทุกทีมในช่วงนี้" }),
  );
  expect(showAll).toHaveBeenCalledOnce();
  expect(screen.getAllByRole("link")).toHaveLength(2);
});
it("links form outcomes to the matching fixture with a readable score and latest label", () => {
  render(<FormBadges results={["W"]} games={[match]} teamId={57} />);
  const link = screen.getByRole("link", {
    name: /ชนะ · นัดล่าสุด: Arsenal 2–1 Chelsea/,
  });
  expect(link).toHaveAttribute("href", "/matches/fixture-1");
  expect(link).toHaveAttribute(
    "title",
    expect.stringContaining("Arsenal 2–1 Chelsea"),
  );
});
