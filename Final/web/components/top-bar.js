import { Suspense } from "react";
import Link from "next/link";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { AccountSlot } from "@/components/app/account-slot";

// App shell top bar (DesignSystem.md section 2): app name and theme toggle on
// every page; on logged-in pages AccountSlot adds the quota indicator and the
// account menu. The step indicator sits under the bar in the (app) layout.
export function TopBar({ appName, children }) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1120px] items-center gap-4 px-4 md:px-6">
        <Link href="/" className="rounded-md" aria-label={`${appName} หน้าแรก`}>
          <Logo name={appName} />
        </Link>
        <div className="flex flex-1 items-center justify-end gap-2">
          {children}
          {/* AccountSlot reads the path (usePathname), which needs a Suspense boundary on dynamic routes */}
          <Suspense fallback={null}>
            <AccountSlot />
          </Suspense>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
