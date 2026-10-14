import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import AdminPage from "../app/admin/[[...section]]/page";
const state = vi.hoisted(() => ({ role: "admin" }));
vi.mock("../components/AppProvider", () => ({
  useApp: () => ({
    user: { id: "admin-id", role: state.role },
    updateRating: vi.fn(),
  }),
}));
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status });
afterEach(() => {
  state.role = "admin";
  vi.useRealTimers();
});
it("a normal user cannot render Admin or fetch admin data", () => {
  state.role = "user";
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  render(<AdminPage params={{}} />);
  expect(screen.getByText(/403/)).toBeInTheDocument();
  expect(fetcher).not.toHaveBeenCalled();
});
it("reports 202 as queued then waits for actual job completion", async () => {
  let polls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      if (path === "/api/admin/pipeline")
        return json({ status: { last_ingest_at: null, quota: {} }, jobs: [] });
      if (path === "/api/admin/pipeline/ingest")
        return json({ job_id: "job-1" }, 202);
      if (path === "/api/admin/jobs/job-1")
        return json({
          job_id: "job-1",
          kind: "ingest",
          status: ++polls === 1 ? "running" : "done",
        });
      throw new Error(path);
    }),
  );
  render(<AdminPage params={{ section: ["pipeline"] }} />);
  await screen.findByText("ยังไม่มีงาน");
  await userEvent.click(screen.getByRole("button", { name: "เริ่มดึงข้อมูล" }));
  await screen.findByText("กำลังทำงาน");
  expect(screen.getByRole("button", { name: "เริ่มดึงข้อมูล" })).toBeDisabled();
  await screen.findByText("สำเร็จ", {}, { timeout: 4000 });
  expect(screen.getByRole("button", { name: "เริ่มดึงข้อมูล" })).toBeEnabled();
});
it("prevents publishing unsaved report changes and asks before unpublishing", async () => {
  const report = {
    season: "2026",
    matchweek: 5,
    title: "Weekly",
    markdown: "## Hello",
    status: "draft",
  };
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.startsWith("/api/admin/reports?"))
      return json({ items: [report] });
    if (init?.method === "PATCH")
      Object.assign(report, JSON.parse(String(init.body)));
    if (path.endsWith("/publish")) report.status = "published";
    return json(report);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<AdminPage params={{ section: ["reports"] }} />);
  await userEvent.click(await screen.findByRole("button", { name: /Weekly/ }));
  await userEvent.type(
    screen.getByRole("textbox", { name: "หัวข้อ" }),
    " updated",
  );
  expect(screen.getByRole("button", { name: "เผยแพร่" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "บันทึกการแก้ไข" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "เผยแพร่" })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole("button", { name: "เผยแพร่" }));
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const count = fetcher.mock.calls.length;
  await userEvent.click(
    await screen.findByRole("button", { name: "ถอนการเผยแพร่" }),
  );
  expect(confirm).toHaveBeenCalled();
  expect(fetcher.mock.calls.length).toBe(count);
});
