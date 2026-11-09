import { Suspense } from "react";
import { RoleDetail } from "@/components/roles/role-detail";

export const metadata = { title: "รายละเอียดสายงาน" };

// Step 4 of 4: role detail (DesignSystem.md section 4, FR-19 – FR-22f).
// RoleDetail reads the role id with useParams, so it needs a Suspense boundary.
export default function RoleDetailPage() {
  return (
    <Suspense>
      <RoleDetail />
    </Suspense>
  );
}
