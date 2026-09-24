import { Activity, Compass, Menu } from "lucide-react";
import Link from "next/link";
import { UserNav } from "@/components/auth/user-nav";

export function SiteHeader() {
  return (
    <header className="absolute inset-x-0 top-0 z-20 mx-auto flex max-w-7xl items-center justify-between px-6 py-6 text-white">
      <Link href="#top" className="flex items-center gap-2 text-lg font-bold tracking-tight">
        <Compass size={21} /> WayPoint
      </Link>
      <nav className="hidden gap-7 text-xs font-bold tracking-wide md:flex">
        <a href="#map" className="transition hover:text-aqua">ROUTE MAP</a>
        <a href="#dashboard" className="transition hover:text-aqua">SAFETY DASHBOARD</a>
        <Link href="/status" className="flex items-center gap-1.5 transition hover:text-aqua">
          <Activity size={13} className="text-emerald-400" /> SYSTEM STATUS
        </Link>
        <a href="#faq" className="transition hover:text-aqua">FAQ</a>
      </nav>
      <div className="flex items-center gap-3">
        <Link
          href="/admin"
          className="rounded-full border border-white/60 px-4 py-2 text-xs font-bold backdrop-blur transition hover:bg-white hover:text-ink"
        >
          ADMIN <Menu className="ml-1 inline" size={14} />
        </Link>
        <UserNav />
      </div>
    </header>
  );
}
