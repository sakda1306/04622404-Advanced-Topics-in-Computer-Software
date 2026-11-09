"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check, ChevronDown, LayoutDashboard, Lock, LogOut, Route, UserRound } from "lucide-react";
import { logout, useHasProfile, useSession } from "@/lib/session";
import { useLandingState } from "@/components/landing/landing-actions";

// Top-bar items (DesignSystem.md section 2). Signed in, on every page: the
// "เส้นทางของฉัน" menu (steps 1–3: start, profile, matched roles; 2 and 3 locked
// until a profile exists, as in the step indicator). Logged-in pages: the quota
// indicator (FR-25) and the account menu. Public pages (landing, login, register) only peek
// at the session: signed out they show เข้าสู่ระบบ / สมัครใช้งาน (not the one for
// the page you are on), signed in the same "continue" button as the landing hero
// plus the account menu.

// /present is the course presentation page: public, linked from nowhere.
const PUBLIC_PATHS = new Set(["/", "/login", "/register", "/present"]);

function QuotaIndicator({ quota }) {
  if (!quota) return null;
  const left = Math.max(0, quota.requests_limit - quota.requests_used);
  const low = quota.exhausted || left / quota.requests_limit < 0.2;
  const resetTime = new Date(quota.reset_at).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" });
  return (
    <span
      className={`hidden items-center gap-1.5 text-small sm:inline-flex ${low ? "font-medium text-warning" : "text-text-muted"}`}
      title={quota.exhausted ? `รีเซ็ตเวลา ${resetTime} น.` : undefined}
    >
      {quota.exhausted ? `ใช้ AI ครบแล้ววันนี้ · รีเซ็ต ${resetTime} น.` : (
        <>
          เหลือ <span className="tabular">{left}/{quota.requests_limit}</span> ครั้งวันนี้
        </>
      )}
    </span>
  );
}

function AccountMenu({ user }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const menuId = useId();

  useDismiss(open, setOpen, wrapRef);

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex min-h-11 items-center gap-2 rounded-md px-2 text-small text-text hover:bg-surface"
      >
        <span className="inline-flex size-8 items-center justify-center rounded-full bg-primary-subtle font-semibold text-text">
          {user.display_name.slice(0, 1)}
        </span>
        <span className="hidden max-w-32 truncate md:inline">{user.display_name}</span>
        <ChevronDown className="size-4 text-text-muted" strokeWidth={1.75} aria-hidden="true" />
      </button>
      {open && (
        <div id={menuId} role="menu" aria-label="บัญชี" className="absolute right-0 z-50 mt-2 w-56 rounded-lg border border-border bg-bg p-1 shadow-md">
          <p className="truncate px-3 pt-2 pb-1 text-tiny text-text-muted">{user.email}</p>
          <a role="menuitem" href="/account" className="flex min-h-11 items-center gap-3 rounded-md px-3 text-small text-text hover:bg-surface">
            <UserRound className="size-4 text-text-muted" strokeWidth={1.5} aria-hidden="true" />
            บัญชีของฉัน
          </a>
          {user.is_admin && (
            <a role="menuitem" href="/admin" className="flex min-h-11 items-center gap-3 rounded-md px-3 text-small text-text hover:bg-surface">
              <LayoutDashboard className="size-4 text-text-muted" strokeWidth={1.5} aria-hidden="true" />
              แดชบอร์ดผู้ดูแล
            </a>
          )}
          <button
            role="menuitem"
            type="button"
            onClick={logout}
            className="flex min-h-11 w-full items-center gap-3 rounded-md px-3 text-left text-small text-text hover:bg-surface"
          >
            <LogOut className="size-4 text-text-muted" strokeWidth={1.5} aria-hidden="true" />
            ออกจากระบบ
          </button>
        </div>
      )}
    </div>
  );
}

// No display class here: each use adds inline-flex, or hidden sm:inline-flex.
const navPrimary =
  "min-h-11 items-center whitespace-nowrap rounded-full bg-primary px-4 text-small font-semibold text-on-primary transition-colors duration-150 hover:bg-primary-hover";
const navGhost =
  "min-h-11 items-center whitespace-nowrap rounded-full px-3 text-small font-semibold text-text transition-colors duration-150 hover:bg-surface sm:px-4";

function PublicNav({ pathname }) {
  const s = useLandingState();
  if (s.state === "checking") return null;
  if (s.state === "in") {
    return (
      <>
        <StepsMenu pathname={pathname} hasProfile={s.hasProfile} />
        <AccountMenu user={s.user} />
      </>
    );
  }
  return (
    <nav aria-label="บัญชี" className="flex items-center gap-1">
      {pathname !== "/login" && (
        // On the landing and presentation pages a phone keeps only สมัครใช้งาน here, so the bar fits.
        <Link href="/login" className={`${navGhost} ${pathname === "/" || pathname === "/present" ? "hidden sm:inline-flex" : "inline-flex"}`}>
          เข้าสู่ระบบ
        </Link>
      )}
      {pathname !== "/register" && (
        <Link href="/register" className={`${navPrimary} inline-flex`}>
          สมัครใช้งาน
        </Link>
      )}
    </nav>
  );
}

const STEPS = [
  { n: 1, label: "ข้อมูลของคุณ", hint: "CV แบบสอบถาม และแชท", href: "/start", needsProfile: false },
  { n: 2, label: "โปรไฟล์", hint: "ทักษะและความชอบในการทำงาน", href: "/profile", needsProfile: true },
  { n: 3, label: "สายงานที่เหมาะ", hint: "สายงานที่ตรงกับคุณ", href: "/roles", needsProfile: true },
];

/** Closes on outside click and Escape. */
function useDismiss(open, setOpen, ref) {
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => !ref.current?.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, setOpen, ref]);
}

function StepsMenu({ pathname, hasProfile }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const menuId = useId();
  useDismiss(open, setOpen, wrapRef);
  const current = STEPS.find((s) => pathname === s.href || (s.href === "/roles" && pathname.startsWith("/roles/")));

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label="เส้นทางของฉัน"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex min-h-11 items-center gap-2 rounded-full border border-border px-3 text-small font-semibold text-text transition-colors duration-150 hover:bg-surface sm:px-4"
      >
        <Route className="size-4 text-accent" strokeWidth={2} aria-hidden="true" />
        <span className="hidden sm:inline">เส้นทางของฉัน</span>
        {current && <span className="hidden text-tiny font-medium text-text-muted md:inline">· {current.label}</span>}
        <ChevronDown className={`size-4 text-text-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`} strokeWidth={1.75} aria-hidden="true" />
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label="เส้นทางของฉัน"
          className="fixed inset-x-3 top-16 z-50 rounded-lg border border-border bg-bg p-1.5 shadow-md sm:absolute sm:inset-x-auto sm:top-auto sm:right-0 sm:mt-2 sm:w-72"
        >
          {STEPS.map((s) => {
            const locked = s.needsProfile && hasProfile === false;
            const here = current?.n === s.n;
            const done = !locked && hasProfile && s.n === 1;
            const badge = (
              <span
                className={`inline-flex size-7 shrink-0 items-center justify-center rounded-full text-tiny font-semibold tabular ${
                  here ? "bg-primary text-on-primary" : done ? "bg-accent text-on-primary" : "border border-border text-text-muted"
                }`}
              >
                {done && !here ? <Check className="size-3.5" strokeWidth={3} aria-hidden="true" /> : s.n}
              </span>
            );
            const text = (
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">{s.label}</span>
                <span className="block text-tiny text-text-muted">{locked ? "สร้างโปรไฟล์ในขั้นที่ 1 ก่อน" : s.hint}</span>
              </span>
            );
            if (locked) {
              return (
                <div key={s.n} role="menuitem" aria-disabled="true" className="flex min-h-12 cursor-not-allowed items-center gap-3 rounded-md px-3 py-2 text-small text-text-muted opacity-70">
                  {badge}
                  {text}
                  <Lock className="size-4" strokeWidth={2} aria-hidden="true" />
                </div>
              );
            }
            return (
              <Link
                key={s.n}
                role="menuitem"
                href={s.href}
                aria-current={here ? "page" : undefined}
                onClick={() => setOpen(false)}
                className={`flex min-h-12 items-center gap-3 rounded-md px-3 py-2 text-small text-text hover:bg-surface ${here ? "bg-surface" : ""}`}
              >
                {badge}
                {text}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function AccountSlot() {
  const pathname = usePathname();
  const isPublic = PUBLIC_PATHS.has(pathname);
  const { status, user, quota } = useSession({ load: !isPublic });
  // Asked again on every page change, so the steps unlock right after a profile is generated.
  const hasProfile = useHasProfile(!isPublic && status === "ready" && Boolean(user), pathname);
  if (isPublic) return <PublicNav pathname={pathname} />;
  if (status !== "ready" || !user) return null;
  return (
    <>
      <QuotaIndicator quota={quota} />
      <StepsMenu pathname={pathname} hasProfile={hasProfile} />
      <AccountMenu user={user} />
    </>
  );
}
