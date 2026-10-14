import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { MascotDock } from "../components/MascotDock";
import { teams } from "../lib/teams";
import { clampPet } from "../lib/pet";
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("../components/AppProvider", () => ({
  useApp: () => ({
    team: teams[0],
    pending: false,
    error: undefined,
    openSignal: 0,
  }),
}));
vi.mock("../components/ChatPanel", () => ({
  ChatPanel: () => <input aria-label="question" />,
}));
it("opens by keyboard, moves with arrows and closes with Escape", async () => {
  render(<MascotDock />);
  const pet = await screen.findByRole("button", {
    name: /มาสคอส Manchester United/,
  });
  pet.focus();
  await userEvent.keyboard("{Enter}");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  const before = parseInt(pet.style.left);
  await userEvent.keyboard("{ArrowLeft}");
  expect(parseInt(pet.style.left)).toBeLessThan(before);
  screen.getByRole("textbox").focus();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(pet).toHaveFocus();
});
it("clamps corrupt saved coordinates and viewport edges", () => {
  expect(clampPet(NaN, Infinity, 375, 667)).toEqual({ x: 205, y: 477 });
  expect(clampPet(9999, -12, 375, 667)).toEqual({ x: 223, y: 8 });
});
