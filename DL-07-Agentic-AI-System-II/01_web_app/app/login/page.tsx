"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  Eye,
  EyeOff,
  Gauge,
  Key,
  Loader2,
  Lock,
  Shield,
  ShieldAlert,
  Sparkles,
  User,
} from "lucide-react";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const router = useRouter();

  const handleLogin = async (targetUser?: string, targetPass?: string, persona?: string) => {
    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    const finalUser = targetUser !== undefined ? targetUser : username;
    const finalPass = targetPass !== undefined ? targetPass : password;

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: finalUser,
          password: finalPass,
          persona,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.message || data.error || "Authentication failed");
      }

      // Store tokens and user profile
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem("access_token", data.access_token);
        window.localStorage.setItem("access_token", data.access_token);

        if (data.user?.role === "admin") {
          window.sessionStorage.setItem("admin_access_token", data.access_token);
          window.localStorage.setItem("admin_access_token", data.access_token);
        } else {
          window.sessionStorage.removeItem("admin_access_token");
          window.localStorage.removeItem("admin_access_token");
        }

        window.sessionStorage.setItem("auth_user", JSON.stringify(data.user));
        window.localStorage.setItem("auth_user", JSON.stringify(data.user));
      }

      setSuccessMsg(`Welcome, ${data.user.name}! Redirecting...`);

      setTimeout(() => {
        if (data.user?.role === "admin") {
          router.push("/admin");
        } else {
          router.push("/");
        }
      }, 700);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in. Please check credentials.");
    } finally {
      setLoading(false);
    }
  };

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("Please fill in both username and password.");
      return;
    }
    handleLogin();
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-[#f8fbff] p-4 text-ink">
      <div className="w-full max-w-xl">
        {/* Back Link */}
        <div className="mb-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-bold text-slate-500 transition hover:text-pine"
          >
            <ArrowLeft size={14} /> Back to WayPoint Map
          </Link>
        </div>

        {/* Card Container */}
        <div className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-float">
          {/* Header */}
          <div className="border-b border-slate-100 bg-gradient-to-b from-slate-50/50 to-white p-8 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-pine text-white shadow-md shadow-pine/20">
              <Gauge size={28} />
            </div>
            <h1 className="font-display text-3xl font-bold text-slate-900">
              WayPoint Authentication
            </h1>
            <p className="mt-1 text-xs text-slate-500">
              Select a persona or enter credentials to generate authorized access tokens.
            </p>
          </div>

          <div className="p-8">
            {/* Quick Demo Persona Selectors */}
            <div className="mb-8">
              <span className="mb-3 block text-xs font-bold uppercase tracking-wider text-slate-400">
                1-Click Quick Connect Personas
              </span>

              <div className="grid gap-3 sm:grid-cols-2">
                {/* Admin Persona */}
                <button
                  type="button"
                  onClick={() => handleLogin("admin", "admin1234", "admin")}
                  disabled={loading}
                  className="group relative flex flex-col items-start rounded-2xl border-2 border-emerald-200 bg-emerald-50/40 p-4 text-left transition hover:border-emerald-500 hover:bg-emerald-50/80 disabled:opacity-50"
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-100 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-emerald-800">
                      <Shield size={11} /> Super Admin
                    </span>
                    <Sparkles size={14} className="text-emerald-500 opacity-60 group-hover:opacity-100" />
                  </div>
                  <h3 className="mt-2.5 text-sm font-bold text-slate-900">
                    Full System Access
                  </h3>
                  <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                    All scopes enabled: Route planner, Admin Jobs, Diagnostics, Safety Reviews, & Audit Logs.
                  </p>
                  <div className="mt-3 flex items-center gap-1 font-mono text-[10px] text-slate-400">
                    User: <strong className="text-slate-700">admin</strong> • Pass: <strong className="text-slate-700">admin1234</strong>
                  </div>
                </button>

                {/* Traveler Persona */}
                <button
                  type="button"
                  onClick={() => handleLogin("dev-user", "dev-password-change-me", "traveler")}
                  disabled={loading}
                  className="group relative flex flex-col items-start rounded-2xl border-2 border-sky-200 bg-sky-50/40 p-4 text-left transition hover:border-sky-500 hover:bg-sky-50/80 disabled:opacity-50"
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 rounded-lg bg-sky-100 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-sky-800">
                      <User size={11} /> Traveler
                    </span>
                    <Sparkles size={14} className="text-sky-500 opacity-60 group-hover:opacity-100" />
                  </div>
                  <h3 className="mt-2.5 text-sm font-bold text-slate-900">
                    Traveler Account
                  </h3>
                  <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                    Route safety queries, live multi-modal assessments, weather alerts, and review submission.
                  </p>
                  <div className="mt-3 flex items-center gap-1 font-mono text-[10px] text-slate-400">
                    User: <strong className="text-slate-700">dev-user</strong> • Pass: <strong className="text-slate-700">dev-password...</strong>
                  </div>
                </button>
              </div>
            </div>

            {/* Divider */}
            <div className="relative mb-6 text-center">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200" />
              </div>
              <span className="relative bg-white px-3 text-[11px] uppercase tracking-wider text-slate-400">
                Or Sign In With Credentials
              </span>
            </div>

            {/* Feedback Alerts */}
            {error && (
              <div className="mb-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-xs text-red-700">
                <ShieldAlert size={16} className="shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {successMsg && (
              <div className="mb-4 flex items-center gap-2 rounded-xl bg-emerald-50 p-3 text-xs font-bold text-emerald-700">
                <CheckCircle2 size={16} className="shrink-0" />
                <span>{successMsg}</span>
              </div>
            )}

            {/* Manual Form */}
            <form onSubmit={handleManualSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="login-username"
                  className="block text-xs font-bold text-slate-700"
                >
                  Username / Client ID
                </label>
                <div className="relative mt-1">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                    <User size={15} />
                  </div>
                  <input
                    id="login-username"
                    name="username"
                    type="text"
                    autoComplete="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="e.g. admin or dev-user"
                    className="w-full rounded-2xl border border-slate-200 py-2.5 pl-10 pr-4 text-xs transition focus:border-pine focus:outline-none focus:ring-2 focus:ring-pine/10"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="login-password"
                  className="block text-xs font-bold text-slate-700"
                >
                  Password / Secret
                </label>
                <div className="relative mt-1">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                    <Lock size={15} />
                  </div>
                  <input
                    id="login-password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter password..."
                    className="w-full rounded-2xl border border-slate-200 py-2.5 pl-10 pr-10 text-xs transition focus:border-pine focus:outline-none focus:ring-2 focus:ring-pine/10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-pine py-3 text-xs font-bold text-white shadow-md shadow-pine/15 transition hover:bg-pine/90 disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Key size={15} />
                )}
                <span>Sign In & Generate Token</span>
              </button>
            </form>
          </div>
        </div>

        {/* Footer info */}
        <p className="mt-6 text-center text-xs text-slate-400">
          WayPoint Travel Safety Intelligence System • Secured via Keycloak OIDC
        </p>
      </div>
    </main>
  );
}
