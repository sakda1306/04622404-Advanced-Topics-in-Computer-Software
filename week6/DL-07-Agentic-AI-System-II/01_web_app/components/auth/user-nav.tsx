"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  Key,
  LogIn,
  LogOut,
  Shield,
  User,
  Users,
} from "lucide-react";

export interface AuthUserProfile {
  username: string;
  name: string;
  role: "admin" | "traveler";
  email: string;
  scopes: string[];
}

export function UserNav() {
  const [profile, setProfile] = useState<AuthUserProfile | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const router = useRouter();

  const syncUser = () => {
    if (typeof window === "undefined") return;

    const rawUser = window.localStorage.getItem("auth_user") || window.sessionStorage.getItem("auth_user");
    if (rawUser) {
      try {
        setProfile(JSON.parse(rawUser));
        return;
      } catch {
        // Fall back to token analysis below
      }
    }

    const token =
      window.sessionStorage.getItem("admin_access_token") ||
      window.localStorage.getItem("admin_access_token") ||
      window.sessionStorage.getItem("access_token") ||
      window.localStorage.getItem("access_token");

    if (!token) {
      setProfile(null);
      return;
    }

    try {
      const parts = token.split(".");
      if (parts.length >= 2) {
        const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
        const scopeStr = payload.scope || "";
        const scopes = typeof scopeStr === "string" ? scopeStr.split(" ") : [];
        const isAdmin = scopes.includes("admin:read");

        setProfile({
          username: isAdmin ? "admin" : (payload.preferred_username || "traveler"),
          name: isAdmin ? "Super Admin" : "Dev Traveler",
          role: isAdmin ? "admin" : "traveler",
          email: isAdmin ? "admin@waypoint.local" : (payload.email || "traveler@example.com"),
          scopes,
        });
        return;
      }
    } catch {
      // Ignore token parse errors
    }

    setProfile(null);
  };

  useEffect(() => {
    syncUser();
    window.addEventListener("storage", syncUser);
    return () => window.removeEventListener("storage", syncUser);
  }, [pathname]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleCopyToken = () => {
    const token =
      window.sessionStorage.getItem("admin_access_token") ||
      window.localStorage.getItem("admin_access_token") ||
      window.sessionStorage.getItem("access_token") ||
      window.localStorage.getItem("access_token");

    if (token) {
      navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleSignOut = () => {
    window.sessionStorage.removeItem("admin_access_token");
    window.localStorage.removeItem("admin_access_token");
    window.sessionStorage.removeItem("access_token");
    window.localStorage.removeItem("access_token");
    window.sessionStorage.removeItem("auth_user");
    window.localStorage.removeItem("auth_user");
    setProfile(null);
    setIsOpen(false);
    router.push("/login");
  };

  if (!profile) {
    return (
      <Link
        href="/login"
        className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-xs font-bold text-white shadow-sm backdrop-blur-md transition hover:bg-white/20"
      >
        <LogIn size={14} className="text-aqua" />
        <span>เข้าสู่ระบบ</span>
      </Link>
    );
  }

  const isAdmin = profile.role === "admin";
  const initials = isAdmin ? "AD" : "TR";

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="inline-flex items-center gap-2.5 rounded-full border border-slate-200/80 bg-white/95 px-3 py-1.5 text-xs shadow-sm backdrop-blur-sm transition hover:border-slate-300 hover:bg-white"
        aria-expanded={isOpen}
      >
        <div
          className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold text-white ${
            isAdmin ? "bg-emerald-600" : "bg-pine"
          }`}
        >
          {initials}
        </div>
        <div className="text-left">
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-slate-800">{profile.name}</span>
            <span
              className={`rounded-full px-1.5 py-0.2 text-[9px] font-extrabold uppercase tracking-wider ${
                isAdmin
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-sky-100 text-sky-800"
              }`}
            >
              {isAdmin ? "ผู้ดูแล" : "ผู้ใช้"}
            </span>
          </div>
        </div>
        <ChevronDown size={14} className="text-slate-400 transition-transform" />
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-72 origin-top-right rounded-2xl border border-slate-200 bg-white p-2 shadow-float focus:outline-none">
          <div className="border-b border-slate-100 px-3 py-2.5">
            <p className="text-xs font-bold text-slate-900">{profile.name}</p>
            <p className="truncate text-[11px] text-slate-500">{profile.email}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {profile.scopes.slice(0, 4).map((s) => (
                <span
                  key={s}
                  className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-mono text-slate-600"
                >
                  {s}
                </span>
              ))}
              {profile.scopes.length > 4 && (
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-mono text-slate-500">
                  +{profile.scopes.length - 4} อื่นๆ
                </span>
              )}
            </div>
          </div>

          <div className="py-1 text-xs">
            {isAdmin && !pathname.startsWith("/admin") && (
              <Link
                href="/admin"
                onClick={() => setIsOpen(false)}
                className="flex items-center gap-2 rounded-xl px-3 py-2 font-medium text-slate-700 transition hover:bg-slate-50"
              >
                <Shield size={14} className="text-emerald-600" />
                <span>คอนโซลผู้ดูแลระบบ</span>
              </Link>
            )}

            {pathname.startsWith("/admin") && (
              <Link
                href="/"
                onClick={() => setIsOpen(false)}
                className="flex items-center gap-2 rounded-xl px-3 py-2 font-medium text-slate-700 transition hover:bg-slate-50"
              >
                <ExternalLink size={14} className="text-pine" />
                <span>ระบบวางแผนการเดินทาง</span>
              </Link>
            )}

            <button
              type="button"
              onClick={handleCopyToken}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left font-medium text-slate-700 transition hover:bg-slate-50"
            >
              {copied ? (
                <Check size={14} className="text-emerald-600" />
              ) : (
                <Copy size={14} className="text-slate-400" />
              )}
              <span>{copied ? "คัดลอกโทเค็นแล้ว!" : "คัดลอกโทเค็นใช้งาน"}</span>
            </button>

            <Link
              href="/login"
              onClick={() => setIsOpen(false)}
              className="flex items-center gap-2 rounded-xl px-3 py-2 font-medium text-slate-700 transition hover:bg-slate-50"
            >
              <Users size={14} className="text-slate-400" />
              <span>สลับบัญชีผู้ใช้</span>
            </Link>
          </div>

          <div className="border-t border-slate-100 pt-1">
            <button
              type="button"
              onClick={handleSignOut}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-bold text-red-600 transition hover:bg-red-50"
            >
              <LogOut size={14} />
              <span>ออกจากระบบ</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
