import { Suspense } from "react";
import { Intake } from "@/components/intake/intake";

export const metadata = { title: "ข้อมูลของคุณ" };

// Step 1 of 4: intake (DesignSystem.md section 4, FR-0 – FR-9, FR-14).
// The step indicator is drawn by Intake, which knows whether a profile exists.
export default function StartPage() {
  return (
    // useSearchParams (the ?tab= value) needs a Suspense boundary
    <Suspense>
      <Intake />
    </Suspense>
  );
}
