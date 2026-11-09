"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useHasProfile, useSession } from "@/lib/session";

// Landing page buttons. Signed out: สมัครใช้งาน / เข้าสู่ระบบ. Signed in, the
// buttons lead back into the app instead: to the profile and matched roles once
// a profile exists, otherwise to step 1. The page only peeks at the session
// (no redirect); until the answer is known the buttons keep their space but stay
// hidden, so a signed-in user never sees "สมัครใช้งาน" flash first.

export function PrimaryCta({ href, children }) {
  return (
    <Link
      href={href}
      className="group inline-flex min-h-12 items-center gap-3 rounded-full bg-hero-cta py-2 pr-2 pl-6 text-body font-semibold text-on-hero-cta shadow-md transition-transform duration-200 ease-out hover:-translate-y-0.5"
    >
      {children}
      <span className="inline-flex size-9 items-center justify-center rounded-full bg-on-hero-cta text-hero-cta transition-transform duration-200 ease-out group-hover:translate-x-0.5">
        <ArrowRight className="size-4" strokeWidth={2} aria-hidden="true" />
      </span>
    </Link>
  );
}

export function SecondaryCta({ href, children }) {
  return (
    <Link
      href={href}
      className="inline-flex min-h-12 items-center rounded-full border border-hero-muted/40 px-6 text-body font-medium text-hero-fg transition-colors duration-200 ease-out hover:bg-hero-fg/10"
    >
      {children}
    </Link>
  );
}

/**
 * Where a signed-in user goes next.
 * @returns {{ state: "checking" | "out" | "in", user?: object, hasProfile?: boolean }}
 */
export function useLandingState() {
  const { status, user } = useSession({ redirect: false });
  const signedIn = status === "ready" && Boolean(user);
  const hasProfile = useHasProfile(signedIn);
  if (status === "anonymous" || status === "error") return { state: "out" };
  if (!signedIn || hasProfile === null) return { state: "checking" };
  return { state: "in", user, hasProfile };
}

function Reveal({ ready, className = "", children }) {
  return (
    <div className={`transition-opacity duration-200 ease-out ${ready ? "opacity-100" : "invisible opacity-0"} ${className}`}>{children}</div>
  );
}

export function HeroActions() {
  const s = useLandingState();
  return (
    <Reveal ready={s.state !== "checking"} className="mt-9">
      <div className="flex flex-wrap items-center justify-center gap-3">
        {s.state === "in" ? (
          s.hasProfile ? (
            <>
              <PrimaryCta href="/profile">ดูโปรไฟล์ของฉัน</PrimaryCta>
              <SecondaryCta href="/roles">สายงานที่เหมาะกับฉัน</SecondaryCta>
            </>
          ) : (
            <>
              <PrimaryCta href="/start">เริ่มสร้างโปรไฟล์</PrimaryCta>
              <SecondaryCta href="/account">บัญชีของฉัน</SecondaryCta>
            </>
          )
        ) : (
          <>
            <PrimaryCta href="/register">สมัครใช้งาน</PrimaryCta>
            <SecondaryCta href="/login">เข้าสู่ระบบ</SecondaryCta>
          </>
        )}
      </div>
      <p className="mt-4 h-6 text-small text-hero-muted">
        {s.state === "in" && `ยินดีต้อนรับกลับ คุณ${s.user.display_name} · ${s.hasProfile ? "ทำต่อจากที่ค้างไว้ได้เลย" : "เริ่มจากขั้นที่ 1 ได้เลย"}`}
      </p>
    </Reveal>
  );
}

export function FinalAction() {
  const s = useLandingState();
  return (
    <Reveal ready={s.state !== "checking"} className="mt-8 flex justify-center">
      {s.state === "in" ? (
        s.hasProfile ? (
          <PrimaryCta href="/profile">ดูโปรไฟล์ของฉัน</PrimaryCta>
        ) : (
          <PrimaryCta href="/start">เริ่มสร้างโปรไฟล์</PrimaryCta>
        )
      ) : (
        <PrimaryCta href="/register">สร้างโปรไฟล์</PrimaryCta>
      )}
    </Reveal>
  );
}
