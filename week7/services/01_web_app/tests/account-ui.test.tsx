import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AppShell } from "../components/AppShell";
import Login from "../app/login/page";
const state = vi.hoisted(() => ({
  path: "/football/fixtures",
  loggingOut: false,
  user: { id: "A", display_name: "Admin", role: "admin" } as object | null,
}));
vi.mock("next/navigation", () => ({
  usePathname: () => state.path,
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock("../components/MascotDock", () => ({ MascotDock: () => null }));
vi.mock("../components/AppProvider", () => ({
  useApp: () => ({
    user: state.user,
    checked: true,
    loggingOut: state.loggingOut,
    team: {
      key: "manchester-united",
      name: "Manchester United",
      color: "red",
      glow: "255,0,0",
    },
    teamError: new Error("บันทึกทีมไม่สำเร็จ"),
    sessions: [],
    changeTeam: vi.fn(),
  }),
}));
afterEach(() => {
  state.user = { id: "A", display_name: "Admin", role: "admin" };
  state.loggingOut = false;
});
it.each(["/", "/football/fixtures", "/admin"])(
  "shows club save errors on %s without opening the mascot",
  (path) => {
    state.path = path;
    render(
      <AppShell>
        <p>Page content</p>
      </AppShell>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("บันทึกทีมไม่สำเร็จ");
  },
);
it("disables login and announces logout while the logout request is pending", () => {
  state.user = null;
  state.loggingOut = true;
  render(<Login />);
  expect(screen.getByRole("status")).toHaveTextContent("กำลังออกจากระบบ");
  expect(
    screen.getByRole("button", { name: /กำลังออกจากระบบ/ }),
  ).toBeDisabled();
});
it("shows registration to guests without redirecting them to login", () => {
  state.path = "/register";
  state.user = null;
  render(
    <AppShell>
      <p>Registration page</p>
    </AppShell>,
  );
  expect(screen.getByText("Registration page")).toBeInTheDocument();
});
