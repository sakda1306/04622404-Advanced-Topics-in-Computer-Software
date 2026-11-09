import { AdminDashboard } from "@/components/admin/admin";

export const metadata = { title: "แดชบอร์ดผู้ดูแล" };

// Admin dashboard (DesignSystem.md section 4, PRD FR-40 – FR-45). No step
// indicator and no chat panel; admins only (User.is_admin, else 403 page).
export default function AdminPage() {
  return <AdminDashboard />;
}
