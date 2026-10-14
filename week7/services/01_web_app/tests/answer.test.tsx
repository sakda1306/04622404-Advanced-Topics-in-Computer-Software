import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Answer, Markdown } from "../components/Answer";
import { dateTime, routeLabels } from "../lib/types";
vi.mock("../components/AppProvider", () => ({
  useApp: () => ({ updateRating: vi.fn() }),
}));
it("renders Markdown and focuses the matching numbered source", async () => {
  render(
    <Answer
      entry={{
        id: "a1",
        role: "assistant",
        content: "**ผลแข่ง** อ้างอิง [2]",
        sources: [
          { ref: 2, title: "Match report", origin: "football-data.org" },
        ],
      }}
    />,
  );
  expect(screen.getByText("ผลแข่ง").tagName).toBe("STRONG");
  const link = screen.getByRole("link", { name: "[2]" });
  expect(link).toHaveAttribute("href", "#main-a1-source-2");
  await userEvent.click(link);
  expect(document.getElementById("main-a1-source-2")).toHaveFocus();
});
it.each([
  ["retrieval_empty", "ไม่พบข้อมูลที่ตรงกับคำถามในครั้งนี้"],
  ["retrieval_down", "คลังข้อมูลไม่พร้อมใช้งานชั่วคราว"],
  [null, "คำตอบนี้ไม่มีแหล่งอ้างอิงแนบมา"],
])(
  "explains %s without inventing evidence or rewriting the answer",
  (fallback, notice) => {
    render(
      <Answer
        feedback={false}
        entry={{
          id: "missing",
          role: "assistant",
          content: "ข้อความต้นฉบับจากระบบ",
          route: "football_rag",
          sources: [],
          trace: { fallback },
          created_at: "2026-09-26T00:00:00Z",
        }}
      />,
    );
    expect(screen.getByText("ข้อความต้นฉบับจากระบบ")).toBeInTheDocument();
    expect(screen.getByText(notice, { exact: false })).toBeInTheDocument();
    expect(
      screen.queryByText("ตอบจากคลังข้อมูลฟุตบอล"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/^ข้อมูล ณ/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  },
);
it("labels general knowledge without claiming that retrieval found no data", () => {
  render(
    <Answer
      feedback={false}
      entry={{
        id: "general",
        role: "assistant",
        content: "คำอธิบายกฎฟุตบอล",
        route: "general_ai",
        sources: [],
      }}
    />,
  );
  expect(
    screen.getByText(
      "คำตอบจากความรู้ทั่วไป ไม่ได้ยืนยันด้วยข้อมูลในคลังฟุตบอล",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText(/ไม่พบข้อมูลที่ตรง/)).not.toBeInTheDocument();
});
it.each(["clarify", "decline", "chat"] as const)(
  "does not label %s as a missing evidence failure",
  (route) => {
    render(
      <Answer
        feedback={false}
        entry={{
          id: "guard",
          role: "assistant",
          content: "กรุณาระบุชื่อทีม",
          route,
          sources: [],
        }}
      />,
    );
    expect(
      screen.queryByText(/ไม่มีแหล่งอ้างอิงแนบมา/),
    ).not.toBeInTheDocument();
  },
);
it("keeps citation links and distinct API source/data timestamps", () => {
  const fetched = "2026-09-24T02:00:00Z",
    asOf = "2026-09-23T10:00:00Z";
  render(
    <Answer
      feedback={false}
      entry={{
        id: "dated",
        role: "assistant",
        content: "รายงาน [1]",
        route: "football_rag",
        sources: [
          {
            ref: 1,
            title: "Verified report",
            doc_id: "report-1",
            origin: "kb",
            fetched_at: fetched,
          },
        ],
        data_as_of: asOf,
      }}
    />,
  );
  expect(screen.getByText("ข้อมูล ณ " + dateTime(asOf))).toBeInTheDocument();
  expect(screen.getByText("kb · " + dateTime(fetched))).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "[1]" })).toHaveAttribute(
    "href",
    "#main-dated-source-1",
  );
});
it("does not execute HTML or javascript links and does not rewrite code citations", () => {
  const { container } = render(
    <Markdown
      text={
        "<script>alert(1)</script>\n\n[bad](javascript:alert%281%29)\n\n`[1]`"
      }
      sources={[{ ref: 1, title: "Source" }]}
    />,
  );
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  expect(container.querySelector("code")?.textContent).toBe("[1]");
  expect(container.querySelector("code a")).toBeNull();
});
it("labels the chat route and shows it in the route filter list", () => {
  expect(routeLabels.chat).toBe("คุยกับผู้ช่วย");
  expect(Object.keys(routeLabels)).toContain("chat");
});
it("shows a chat answer with no general-knowledge warning", () => {
  render(
    <Answer
      feedback={false}
      entry={{
        id: "chat",
        role: "assistant",
        content: "สวัสดีครับ ผมคือผู้ช่วยฟุตบอล",
        route: "chat",
        sources: [],
      }}
    />,
  );
  expect(screen.getByText("สวัสดีครับ ผมคือผู้ช่วยฟุตบอล")).toBeInTheDocument();
  expect(screen.queryByText(/ความรู้ทั่วไป/)).not.toBeInTheDocument();
  expect(screen.queryByText(/ไม่มีแหล่งอ้างอิงแนบมา/)).not.toBeInTheDocument();
});
