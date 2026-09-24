"use client";

import { useEffect, useState, useCallback } from "react";
import { CheckCircle2, Key, Loader2, LogOut, ShieldAlert, Sparkles, RefreshCw } from "lucide-react";
import { fetchOpsAdminToken, getAccessToken } from "@/lib/api";

interface AdminAuthBarProps {
  onTokenChange?: () => void;
}

function parseJwtScopes(token: string | null): string[] {
  if (!token) return [];
  try {
    const parts = token.split(".");
    if (parts.length < 2) return [];
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    const parsed = JSON.parse(jsonPayload);
    const scopeStr = parsed.scope ?? "";
    return typeof scopeStr === "string" ? scopeStr.split(" ") : [];
  } catch {
    return [];
  }
}

export function AdminAuthBar({ onTokenChange }: AdminAuthBarProps) {
  const [token, setToken] = useState<string | null>(null);
  const [scopes, setScopes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showManualInput, setShowManualInput] = useState(false);
  const [manualToken, setManualToken] = useState("");

  const handleQuickConnect = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOpsAdminToken();
      if (data.access_token) {
        window.sessionStorage.setItem("admin_access_token", data.access_token);
        window.localStorage.setItem("admin_access_token", data.access_token);
        window.sessionStorage.setItem("access_token", data.access_token);
        window.localStorage.setItem("access_token", data.access_token);
        setToken(data.access_token);
        setScopes(parseJwtScopes(data.access_token));
        onTokenChange?.();
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "ไม่สามารถรับโทเค็น ops-admin จากระบบยืนยันตัวตนได้",
      );
    } finally {
      setLoading(false);
    }
  }, [onTokenChange]);

  useEffect(() => {
    const current = getAccessToken();
    const tokenScopes = parseJwtScopes(current);
    setToken(current);
    setScopes(tokenScopes);

    const hasAdminRead = tokenScopes.includes("admin:read");
    if (!current || !hasAdminRead) {
      handleQuickConnect();
    }
  }, [handleQuickConnect]);

  const handleApplyManualToken = () => {
    if (!manualToken.trim()) return;
    const cleanToken = manualToken.trim();
    window.sessionStorage.setItem("admin_access_token", cleanToken);
    window.localStorage.setItem("admin_access_token", cleanToken);
    window.sessionStorage.setItem("access_token", cleanToken);
    window.localStorage.setItem("access_token", cleanToken);
    setToken(cleanToken);
    setScopes(parseJwtScopes(cleanToken));
    setShowManualInput(false);
    setManualToken("");
    onTokenChange?.();
  };

  const handleClearToken = () => {
    window.sessionStorage.removeItem("admin_access_token");
    window.localStorage.removeItem("admin_access_token");
    window.sessionStorage.removeItem("access_token");
    window.localStorage.removeItem("access_token");
    setToken(null);
    setScopes([]);
    onTokenChange?.();
  };

  const hasAdmin = scopes.includes("admin:read");

  return (
    <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className={`flex h-9 w-9 items-center justify-center rounded-xl ${
              hasAdmin
                ? "bg-emerald-50 text-emerald-600"
                : "bg-amber-50 text-amber-600"
            }`}
          >
            {hasAdmin ? <CheckCircle2 size={18} /> : <Key size={18} />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-slate-900">
                การยืนยันตัวตนระดับผู้ดูแลระบบ
              </span>
              <span
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                  hasAdmin
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-amber-100 text-amber-800"
                }`}
              >
                {hasAdmin ? "ยืนยันตัวตนแล้ว (Ops Admin)" : "จำเป็นต้องใช้โทเค็นผู้ดูแลระบบ"}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-slate-500">
              {hasAdmin
                ? `ขอบเขตสิทธิ์ที่ได้รับอนุมัติ (Scopes): ${scopes.join(", ")}`
                : "จำเป็นต้องใช้ Bearer Token ที่มีสิทธิ์ (admin:read, admin:write, safety:review) เพื่อเข้าถึงข้อมูลระบบ"}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!hasAdmin ? (
            <>
              <button
                type="button"
                onClick={handleQuickConnect}
                disabled={loading}
                className="inline-flex items-center gap-1.5 rounded-xl bg-pine px-3.5 py-2 text-xs font-bold text-white transition hover:bg-pine/90 disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Sparkles size={14} className="text-[#b9e5fb]" />
                )}
                เชื่อมต่อ Ops Admin
              </button>
              <button
                type="button"
                onClick={() => setShowManualInput(!showManualInput)}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100"
              >
                ป้อนโทเค็นด้วยตนเอง
              </button>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleQuickConnect}
                disabled={loading}
                title="ต่ออายุโทเค็น"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                ต่ออายุโทเค็น
              </button>
              <button
                type="button"
                onClick={handleClearToken}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 hover:bg-red-50 hover:text-red-700"
              >
                <LogOut size={13} /> ตัดการเชื่อมต่อ
              </button>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-3 flex items-center gap-2 rounded-xl bg-red-50 p-2.5 text-xs text-red-700">
          <ShieldAlert size={14} className="shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {showManualInput && !hasAdmin && (
        <div className="mt-3 flex gap-2 border-t border-slate-100 pt-3">
          <input
            type="text"
            placeholder="วาง Bearer JWT Token พร้อมสิทธิ์ผู้ดูแลระบบที่นี่..."
            value={manualToken}
            onChange={(e) => setManualToken(e.target.value)}
            className="flex-1 rounded-xl border border-slate-200 px-3 py-1.5 text-xs focus:border-pine focus:outline-none"
          />
          <button
            type="button"
            onClick={handleApplyManualToken}
            className="rounded-xl bg-slate-900 px-4 py-1.5 text-xs font-bold text-white hover:bg-slate-800"
          >
            นำไปใช้
          </button>
        </div>
      )}
    </div>
  );
}
