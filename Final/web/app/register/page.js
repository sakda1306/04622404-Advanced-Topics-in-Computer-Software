import { AuthShell } from "@/components/auth/auth-shell";
import { RegisterForm } from "@/components/auth/auth-form";

export const metadata = { title: "สมัครใช้งาน" };

// Register (DesignSystem.md section 4, FR-26): display name, email, password and
// the required consent checkbox.
export default function RegisterPage() {
  return (
    <AuthShell title="สมัครใช้งาน" subtitle="เริ่มเห็นภาพตัวเองชัดขึ้นไปด้วยกัน" cardTitle="สร้างบัญชีของคุณ">
      <RegisterForm />
    </AuthShell>
  );
}
