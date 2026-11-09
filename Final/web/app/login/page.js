import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/auth-form";

export const metadata = { title: "เข้าสู่ระบบ" };

// Login (DesignSystem.md section 4, FR-26): email and password.
export default function LoginPage() {
  return (
    <AuthShell title="ยินดีต้อนรับกลับ" subtitle="เริ่มเห็นภาพตัวเองชัดขึ้นไปด้วยกัน" cardTitle="เข้าสู่ระบบด้วยอีเมล">
      <LoginForm />
    </AuthShell>
  );
}
