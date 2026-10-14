import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import Register from "../app/register/page";

const register = vi.hoisted(() => vi.fn());
vi.mock("../components/AppProvider", () => ({
  useApp: () => ({ user: null, checked: true, register }),
}));
vi.mock("../components/AuthStory", () => ({ AuthStory: () => null }));

beforeEach(() => register.mockReset().mockResolvedValue(undefined));

function fillForm(confirmation = "long-pass-123") {
  fireEvent.change(screen.getByRole("textbox", { name: /ชื่อผู้ใช้/ }), {
    target: { value: "new_fan" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "ชื่อที่แสดง" }), {
    target: { value: "Football Fan" },
  });
  fireEvent.change(screen.getByLabelText(/^รหัสผ่าน/), {
    target: { value: "long-pass-123" },
  });
  fireEvent.change(screen.getByLabelText("ยืนยันรหัสผ่าน"), {
    target: { value: confirmation },
  });
}

it("submits a new username and password", async () => {
  render(<Register />);
  fillForm();
  fireEvent.submit(
    screen.getByRole("button", { name: "สมัครสมาชิก" }).closest("form")!,
  );
  await waitFor(() =>
    expect(register).toHaveBeenCalledWith(
      "new_fan",
      "Football Fan",
      "long-pass-123",
    ),
  );
});

it("shows a password confirmation error without sending the request", async () => {
  render(<Register />);
  fillForm("different-pass");
  fireEvent.submit(
    screen.getByRole("button", { name: "สมัครสมาชิก" }).closest("form")!,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "รหัสผ่านทั้งสองช่องไม่ตรงกัน",
  );
  expect(register).not.toHaveBeenCalled();
});
