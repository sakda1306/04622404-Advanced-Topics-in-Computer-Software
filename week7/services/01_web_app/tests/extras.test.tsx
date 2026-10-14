import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { KnowledgeBase, Users } from "../components/AdminExtras";
vi.mock("../components/AppProvider", () => ({
  useApp: () => ({ user: { id: "self" } }),
}));
it("disables own role and account controls", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            items: [
              {
                id: "self",
                username: "admin",
                display_name: "Admin",
                role: "admin",
                disabled: false,
                message_count: 0,
              },
            ],
            next_cursor: null,
          }),
        ),
    ),
  );
  render(<Users />);
  expect(
    await screen.findByRole("combobox", { name: "บทบาท admin" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "ระงับบัญชี" })).toBeDisabled();
});
it("treats rebuild acceptance as pending and does not call a nonexistent polling API", async () => {
  const fetcher = vi.fn(async (input: RequestInfo | URL) =>
    String(input).endsWith("/reindex")
      ? new Response(JSON.stringify({ job_id: "rebuild-123" }), { status: 202 })
      : new Response(
          JSON.stringify({
            documents: 3,
            chunks: 3,
            by_category: {},
            index_version: "test",
          }),
        ),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<KnowledgeBase />);
  await screen.findByText("Index version: test");
  await userEvent.click(
    screen.getByRole("button", { name: "เริ่มสร้างดัชนี" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "rebuild-123 · ยังไม่ใช่การยืนยันว่าเสร็จสิ้น",
  );
  expect(fetcher).toHaveBeenCalledTimes(2);
});
it("shows index startup as retryable failure and recovers KB stats", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          code: "INDEX_NOT_READY",
          detail: "Starting",
          request_id: "kb-start",
        }),
        { status: 503 },
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          documents: 3,
          chunks: 3,
          by_category: {},
          index_version: "ready",
        }),
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  render(<KnowledgeBase />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "คลังข้อมูลกำลังเตรียมพร้อม",
  );
  await userEvent.click(screen.getByRole("button", { name: "ลองใหม่" }));
  expect(await screen.findByText("Index version: ready")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("does not delete a document after confirmation is cancelled", async () => {
  const fetcher = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          documents: 3,
          chunks: 3,
          by_category: {},
          index_version: "test",
        }),
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<KnowledgeBase />);
  await screen.findByText("Index version: test");
  await userEvent.type(
    screen.getByRole("textbox", { name: "Document ID" }),
    "trivia-0001",
  );
  await userEvent.click(screen.getByRole("button", { name: "ลบเอกสาร" }));
  expect(confirm).toHaveBeenCalled();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("offers the historical archive category for reindexing", async () => {
  const fetcher = vi.fn(async (input: RequestInfo | URL) =>
    String(input).endsWith("/reindex")
      ? new Response(JSON.stringify({ job_id: "historical-job" }), {
          status: 202,
        })
      : new Response(
          JSON.stringify({
            documents: 1,
            chunks: 1,
            by_category: { historical: 1 },
            index_version: "archive",
          }),
        ),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<KnowledgeBase />);
  await screen.findByText("Index version: archive");
  const select = screen.getByRole("combobox", { name: "ประเภท" });
  await userEvent.selectOptions(select, "historical");
  await userEvent.click(
    screen.getByRole("button", { name: "เริ่มสร้างดัชนี" }),
  );
  expect(fetcher).toHaveBeenCalledWith(
    "/api/admin/kb/reindex",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ category: "historical" }),
    }),
  );
});

it("shows player and posts only the selected category to the existing reindex API", async () => {
  const fetcher = vi.fn(async (input: RequestInfo | URL) =>
    String(input).endsWith("/reindex")
      ? new Response(JSON.stringify({ job_id: "player-job" }), { status: 202 })
      : new Response(
          JSON.stringify({
            documents: 1,
            chunks: 1,
            by_category: { player: 1 },
            index_version: "players",
          }),
        ),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<KnowledgeBase />);
  await screen.findByText("Index version: players");
  const select = screen.getByRole("combobox", { name: "ประเภท" });
  expect(screen.getByRole("option", { name: "player" })).toBeInTheDocument();
  await userEvent.selectOptions(select, "player");
  await userEvent.click(
    screen.getByRole("button", { name: "เริ่มสร้างดัชนี" }),
  );
  expect(fetcher).toHaveBeenCalledWith(
    "/api/admin/kb/reindex",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ category: "player" }),
    }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "ยังไม่ใช่การยืนยันว่าเสร็จสิ้น",
  );
});

it("keeps all-category requests empty", async () => {
  const fetcher = vi.fn(
    async (input: RequestInfo | URL) =>
      new Response(
        JSON.stringify(
          String(input).endsWith("/reindex")
            ? { job_id: "all" }
            : {
                documents: 0,
                chunks: 0,
                by_category: {},
                index_version: "all",
              },
        ),
        { status: String(input).endsWith("/reindex") ? 202 : 200 },
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<KnowledgeBase />);
  await screen.findByText("Index version: all");
  await userEvent.click(
    screen.getByRole("button", { name: "เริ่มสร้างดัชนี" }),
  );
  expect(fetcher).toHaveBeenCalledWith(
    "/api/admin/kb/reindex",
    expect.objectContaining({ body: "{}" }),
  );
});
