import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ErrorBox } from "../components/Ui";
import { ApiError } from "../lib/api";

it.each([
  [503, "INDEX_NOT_READY", "คลังข้อมูลกำลังเตรียมพร้อม"],
  [502, "RETRIEVAL_UNAVAILABLE", "เชื่อมต่อคลังข้อมูลไม่ได้ชั่วคราว"],
] as const)(
  "provides recovery for %s %s and retains diagnostics",
  async (status, code, text) => {
    const retry = vi.fn();
    render(
      <ErrorBox
        error={
          new ApiError(status, code, "Upstream unavailable", "request-123")
        }
        retry={retry}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(text);
    expect(screen.getByText(code)).toBeInTheDocument();
    expect(screen.getByText("Request ID: request-123")).toBeInTheDocument();
    expect(screen.queryByText(/ไม่พบข้อมูล/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ลองใหม่" }));
    expect(retry).toHaveBeenCalledTimes(1);
  },
);
it("preserves an unknown problem detail and retry delay", () => {
  render(
    <ErrorBox
      error={
        new ApiError(429, "RATE_LIMITED", "ส่งคำถามถี่เกินไป", "limited", 12)
      }
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("ส่งคำถามถี่เกินไป");
  expect(screen.getByText("กรุณารอ 12 วินาที")).toBeInTheDocument();
});
