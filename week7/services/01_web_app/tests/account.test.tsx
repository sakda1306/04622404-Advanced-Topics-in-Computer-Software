import { act, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AppProvider, useApp } from "../components/AppProvider";
import { ChatPanel } from "../components/ChatPanel";
const navigation = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  usePathname: () => "/",
}));
let app: ReturnType<typeof useApp>;
function Probe() {
  app = useApp();
  return <span>{app.user?.id ?? "guest"}</span>;
}
const user = (id: string) => ({
  id,
  display_name: id,
  username: id,
  role: "user",
  favorite_team_id: 66,
  language: "th",
});
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
async function setup() {
  const fetcher = vi.fn(
    async (path: string, init?: RequestInit): Promise<Response> => {
      if (path === "/api/auth/me") return json({ user: user("A") });
      if (path === "/api/auth/login") return json({ user: user("B") });
      if (path === "/api/auth/register") return json({ user: user("C") }, 201);
      if (path === "/api/sessions") return json({ sessions: [] });
      if (path === "/api/auth/logout") return json({ ok: true });
      if (path === "/api/me/preferences")
        return json({
          user: {
            ...user("A"),
            favorite_team_id: JSON.parse(String(init?.body)).favorite_team_id,
          },
        });
      if (path === "/api/chat")
        return json({
          session_id: "session-A",
          message_id: crypto.randomUUID(),
          answer: "private answer A",
          sources: [],
          route: "general_ai",
          latency_ms: 10,
        });
      throw new Error("unexpected " + path);
    },
  );
  vi.stubGlobal("fetch", fetcher);
  render(
    <AppProvider>
      <Probe />
      <ChatPanel />
    </AppProvider>,
  );
  await waitFor(() => expect(app.user?.id).toBe("A"));
  return fetcher;
}
it("clears every account's conversation and sends a fresh session after logout/login", async () => {
  const fetcher = await setup();
  await act(async () => {
    await app.sendQuestion("private question A");
  });
  expect(app.entries).toHaveLength(2);
  await act(async () => {
    await app.logout();
    await app.login("B", "password");
  });
  expect(app.entries).toEqual([]);
  expect(app.sessionId).toBeNull();
  await act(async () => {
    await app.sendQuestion("new question B");
  });
  const calls = fetcher.mock.calls.filter(([path]) => path === "/api/chat");
  expect(JSON.parse(String(calls[1][1]?.body)).session_id).toBeNull();
  expect(screen.queryByText("private question A")).not.toBeInTheDocument();
});
it("accepts a newly registered account and opens the home page", async () => {
  const fetcher = await setup();
  await act(async () => {
    await app.register("new_fan", "Football Fan", "long-pass-123");
  });
  expect(app.user?.id).toBe("C");
  expect(navigation.replace).toHaveBeenLastCalledWith("/");
  const request = fetcher.mock.calls.find(
    ([path]) => path === "/api/auth/register",
  );
  expect(JSON.parse(String(request?.[1]?.body))).toEqual({
    username: "new_fan",
    display_name: "Football Fan",
    password: "long-pass-123",
  });
});
it("expires the account on 401 and ignores a late answer after switching identity", async () => {
  const fetcher = await setup();
  fetcher.mockResolvedValueOnce(
    json({ detail: "expired", code: "UNAUTHENTICATED" }, 401),
  );
  await act(async () => {
    await app.sendQuestion("expire");
  });
  expect(app.user).toBeNull();
  expect(app.entries).toEqual([]);
  expect(app.sessions).toEqual([]);
  expect(navigation.replace).toHaveBeenCalledWith("/login?expired=1");
});
it("does not append pending account A response after B logs in", async () => {
  const fetcher = await setup();
  let resolve!: (value: Response) => void;
  fetcher.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  let pending!: Promise<boolean>;
  act(() => {
    pending = app.sendQuestion("old question");
  });
  await act(async () => {
    await app.login("B", "pw");
  });
  await act(async () => {
    resolve(
      json({
        session_id: "old",
        message_id: "old-answer",
        answer: "secret",
        sources: [],
      }),
    );
    await pending;
  });
  expect(app.user?.id).toBe("B");
  expect(app.entries).toEqual([]);
  expect(app.sessionId).toBeNull();
});
it("retains failed draft and never sends while a team preference is pending", async () => {
  const fetcher = await setup();
  act(() => app.setDraft("retry this"));
  fetcher.mockResolvedValueOnce(
    json({ detail: "offline", code: "API_UNAVAILABLE" }, 502),
  );
  await act(async () => {
    expect(await app.sendQuestion("retry this")).toBe(false);
  });
  expect(app.draft).toBe("retry this");
  expect(app.entries).toEqual([]);
  let resolve!: (value: Response) => void;
  fetcher.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  let changing!: Promise<boolean>;
  act(() => {
    changing = app.changeTeam("chelsea");
  });
  await act(async () => {
    expect(await app.sendQuestion("team question")).toBe(false);
  });
  await act(async () => {
    resolve(json({ user: { ...user("A"), favorite_team_id: 61 } }));
    await changing;
  });
  expect(app.team.key).toBe("chelsea");
  expect(app.sessionId).toBeNull();
});
it("sample prompt fills the composer and focuses it", async () => {
  await setup();
  const { default: userEvent } = await import("@testing-library/user-event");
  act(() => app.ask("เล่าประวัติของ Manchester United"));
  expect(screen.getByRole("textbox", { name: "ถามเรื่องฟุตบอล" })).toHaveValue(
    "เล่าประวัติของ Manchester United",
  );
  expect(
    screen.getByRole("textbox", { name: "ถามเรื่องฟุตบอล" }),
  ).toHaveFocus();
});
it.each([200, 502, 504, "network"])(
  "serializes login behind logout (%s) and deduplicates logout",
  async (status) => {
    const fetcher = await setup();
    let release!: () => void;
    fetcher.mockImplementationOnce(
      () =>
        new Promise((resolve, reject) => {
          release = () =>
            status === "network"
              ? reject(new TypeError("offline"))
              : resolve(
                  json(
                    { ok: status === 200, detail: "logout failed" },
                    Number(status),
                  ),
                );
        }),
    );
    let leaving!: Promise<void>, entering!: Promise<void>;
    act(() => {
      leaving = app.logout();
      expect(app.logout()).toBe(leaving);
      entering = app.login("B", "pw");
    });
    expect(app.loggingOut).toBe(true);
    expect(
      fetcher.mock.calls.filter(([path]) => path === "/api/auth/login"),
    ).toHaveLength(0);
    await act(async () => {
      release();
      await leaving;
      await entering;
    });
    expect(app.user?.id).toBe("B");
    expect(app.loggingOut).toBe(false);
    expect(navigation.replace).toHaveBeenLastCalledWith("/");
    expect(
      fetcher.mock.calls.filter(([path]) => path === "/api/auth/logout"),
    ).toHaveLength(1);
  },
);
it("clears a missing history session and sends the next question with a null session", async () => {
  const fetcher = await setup();
  fetcher.mockResolvedValueOnce(json({ detail: "missing" }, 404));
  await act(async () => {
    await app.selectSession("missing");
  });
  expect(app.sessionId).toBeNull();
  expect(app.historyTarget).toBeNull();
  expect(app.error?.message).toMatch(/ไม่พบบทสนทนา/);
  await act(async () => {
    await app.sendQuestion("fresh");
  });
  const call = fetcher.mock.calls.find(([path]) => path === "/api/chat")!;
  expect(JSON.parse(String(call[1]?.body)).session_id).toBeNull();
});
it("blocks sending after transient history failure and resumes after retry", async () => {
  const fetcher = await setup();
  fetcher.mockResolvedValueOnce(json({ detail: "temporary" }, 502));
  await act(async () => {
    await app.selectSession("old");
  });
  expect(app.historyTarget).toBe("old");
  expect(await app.sendQuestion("blocked")).toBe(false);
  expect(fetcher.mock.calls.some(([path]) => path === "/api/chat")).toBe(false);
  expect(screen.getByRole("button", { name: "ลองใหม่" })).toBeEnabled();
  fetcher.mockResolvedValueOnce(json({ messages: [] }));
  await act(async () => {
    await app.selectSession("old");
  });
  expect(app.historyTarget).toBeNull();
  expect(app.sessionId).toBe("old");
  await act(async () => {
    await app.sendQuestion("continue");
  });
  expect(
    JSON.parse(
      String(
        fetcher.mock.calls.find(([path]) => path === "/api/chat")![1]?.body,
      ),
    ).session_id,
  ).toBe("old");
});
it("ignores late history after starting a new conversation", async () => {
  const fetcher = await setup();
  let resolve!: (response: Response) => void;
  fetcher.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  let loading!: Promise<void>;
  act(() => {
    loading = app.selectSession("old");
  });
  act(() => app.newChat());
  await act(async () => {
    resolve(
      json({
        messages: [{ message_id: "secret", role: "assistant", content: "old" }],
      }),
    );
    await loading;
  });
  expect(app.sessionId).toBeNull();
  expect(app.entries).toEqual([]);
  expect(app.historyTarget).toBeNull();
});
it("preserves club and conversation when saving the club fails and clears the error on success", async () => {
  const fetcher = await setup();
  await act(async () => {
    await app.sendQuestion("keep");
  });
  fetcher.mockResolvedValueOnce(json({ detail: "cannot save club" }, 502));
  await act(async () => {
    await app.changeTeam("chelsea");
  });
  expect(app.team.key).toBe("manchester-united");
  expect(app.entries).toHaveLength(2);
  expect(app.teamError?.message).toBe("cannot save club");
  expect(app.error).toBeUndefined();
  await act(async () => {
    await app.changeTeam("chelsea");
  });
  expect(app.team.key).toBe("chelsea");
  expect(app.entries).toHaveLength(2);
  expect(app.teamError).toBeUndefined();
});

it("browses independently of favorite and never PATCHes preferences on chat", async () => {
  const fetcher = await setup();
  await act(async () => {
    await app.sendQuestion("keep session");
  });
  const id = app.sessionId;
  fetcher.mockClear();
  act(() => app.browseTeam("arsenal"));
  expect(app.browsingTeam.teamId).toBe(57);
  expect(app.team.teamId).toBe(66);
  expect(app.user?.favorite_team_id).toBe(66);
  expect(app.sessionId).toBe(id);
  await act(async () => {
    await app.sendQuestion("Arsenal ล่าสุด");
  });
  expect(
    fetcher.mock.calls.some(([path]) => path.includes("/preferences")),
  ).toBe(false);
  await act(async () => {
    await app.changeTeam("manchester-city");
  });
  expect(app.team.teamId).toBe(65);
  expect(app.browsingTeam.teamId).toBe(57);
  expect(app.sessionId).toBe(id);
});
it("resets browsing state on identity switch", async () => {
  await setup();
  act(() => app.browseTeam("arsenal"));
  await act(async () => {
    await app.login("B", "pw");
  });
  expect(app.browsingTeam.teamId).toBe(66);
});

it("sends original follow-up text in the same session and resets context for a new chat", async () => {
  const fetcher = await setup();
  await act(async () => {
    await app.sendQuestion("ลิเวอร์พูลมีโอกาสได้แชมป์กี่เปอร์เซ็นต์?");
  });
  await act(async () => {
    await app.sendQuestion("แล้วอาร์เซนอลล่ะ");
  });
  act(() => app.newChat());
  await act(async () => {
    await app.sendQuestion("ใครจะได้แชมป์");
  });
  const requests = fetcher.mock.calls
    .filter(([path]) => path === "/api/chat")
    .map(([, init]) => JSON.parse(String(init?.body)));
  expect(requests.map((item) => item.session_id)).toEqual([
    null,
    "session-A",
    null,
  ]);
  expect(requests[1].message).toBe("แล้วอาร์เซนอลล่ะ");
});
