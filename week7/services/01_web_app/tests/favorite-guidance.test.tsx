import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { AppProvider, useApp } from "../components/AppProvider";
import { AppShell } from "../components/AppShell";
import { ChatPanel } from "../components/ChatPanel";
import { SuggestedQuestions } from "../components/SuggestedQuestions";

const navigation = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => navigation,
}));
vi.mock("../components/MascotDock", () => ({
  MascotDock: () => <ChatPanel surface="dock" />,
}));
let app: ReturnType<typeof useApp>;
function Probe() {
  app = useApp();
  return null;
}
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status });
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
function setup(favorite: number | null = null, loggedIn = true) {
  const user = {
    id: "guidance",
    username: "demo",
    display_name: "Demo",
    role: "user",
    favorite_team_id: favorite,
    language: "th",
  };
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === "/api/auth/me")
      return loggedIn ? json({ user }) : json({ detail: "not signed in" }, 401);
    if (path === "/api/sessions") return json({ sessions: [] });
    if (path.includes("/football/fixtures")) return json({ matches: [] });
    if (path === "/api/me/preferences")
      return json({
        user: {
          ...user,
          favorite_team_id: JSON.parse(String(init?.body)).favorite_team_id,
        },
      });
    if (path === "/api/chat")
      return json({
        session_id: "new",
        message_id: "answer",
        answer: "test",
        sources: [],
        route: "clarify",
        latency_ms: 1,
      });
    throw new Error("Unexpected " + path);
  });
  vi.stubGlobal("fetch", fetcher);
  render(
    <AppProvider>
      <Probe />
      {loggedIn ? (
        <AppShell>
          <p>Home</p>
        </AppShell>
      ) : (
        <SuggestedQuestions />
      )}
    </AppProvider>,
  );
  return fetcher;
}
it("shows guidance only for a signed-in user without a favorite", async () => {
  setup();
  expect(
    await screen.findByRole("region", { name: "แนะนำการตั้งทีมโปรด" }),
  ).toHaveTextContent("ยังไม่ได้ตั้งทีมโปรด");
});
it.each([true, false])(
  "hides guidance for an existing favorite or guest (signed in=%s)",
  async (loggedIn) => {
    setup(65, loggedIn);
    await waitFor(() => expect(app.checked).toBe(true));
    expect(
      screen.queryByRole("region", { name: "แนะนำการตั้งทีมโปรด" }),
    ).not.toBeInTheDocument();
  },
);
it("opens shared settings, preserves draft on cancel, and saves the default theme only on explicit confirmation", async () => {
  const fetcher = setup();
  await screen.findByRole("button", { name: "ตั้งทีมโปรด" });
  await userEvent.type(
    screen.getByRole("textbox", { name: "ถามเรื่องฟุตบอล" }),
    "ทีมฉัน",
  );
  await userEvent.click(screen.getByRole("button", { name: "ตั้งทีมโปรด" }));
  expect(
    screen.getByRole("dialog", { name: "ตั้งค่าส่วนตัว" }),
  ).toBeInTheDocument();
  expect(
    fetcher.mock.calls.some(([path]) => path === "/api/me/preferences"),
  ).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "ยกเลิก" }));
  expect(screen.getByRole("textbox", { name: "ถามเรื่องฟุตบอล" })).toHaveValue(
    "ทีมฉัน",
  );
  expect(
    fetcher.mock.calls.some(([path]) => path === "/api/me/preferences"),
  ).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "ตั้งทีมโปรด" }));
  await userEvent.click(
    screen.getByRole("button", { name: "บันทึกการตั้งค่า" }),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("region", { name: "แนะนำการตั้งทีมโปรด" }),
    ).not.toBeInTheDocument(),
  );
  expect(app.user?.favorite_team_id).toBe(66);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(app.draft).toBe("ทีมฉัน");
  expect(
    fetcher.mock.calls.filter(([path]) => path === "/api/me/preferences"),
  ).toHaveLength(1);
});
it("keeps guidance and settings on save failure", async () => {
  const fetcher = setup();
  await userEvent.click(
    await screen.findByRole("button", { name: "ตั้งทีมโปรด" }),
  );
  fetcher.mockResolvedValueOnce(json({ detail: "save failed" }, 503));
  await userEvent.click(
    screen.getByRole("button", { name: "บันทึกการตั้งค่า" }),
  );
  await waitFor(() => expect(app.teamError).toBeDefined());
  expect(app.user?.favorite_team_id).toBeNull();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(
    screen.getByRole("region", { name: "แนะนำการตั้งทีมโปรด" }),
  ).toBeInTheDocument();
});
it("does not save a favorite when browsing or sending a question", async () => {
  const fetcher = setup();
  await screen.findByRole("button", { name: "ตั้งทีมโปรด" });
  act(() => app.browseTeam("arsenal"));
  await act(async () => {
    await app.sendQuestion("Arsenal นัดต่อไปเจอใคร");
  });
  expect(app.user?.favorite_team_id).toBeNull();
  expect(
    fetcher.mock.calls.some(([path]) => path === "/api/me/preferences"),
  ).toBe(false);
});
