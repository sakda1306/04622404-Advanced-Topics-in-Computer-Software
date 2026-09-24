"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  CircleHelp,
  Database,
  FileDown,
  Gauge,
  Layers,
  RefreshCw,
  ShieldAlert,
  Users,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminAuditTab } from "@/components/admin/admin-audit-tab";
import { AdminAuthBar } from "@/components/admin/admin-auth-bar";
import { AdminExportsTab } from "@/components/admin/admin-exports-tab";
import { AdminJobsTab } from "@/components/admin/admin-jobs-tab";
import { AdminReviewsTab } from "@/components/admin/admin-reviews-tab";
import { UserNav } from "@/components/auth/user-nav";
import { api, fetchServiceStatus, type ComponentState } from "@/lib/api";

type TabId = "overview" | "jobs" | "reviews" | "audit" | "exports";

const SERVICE_CARD_CONFIG = [
  { name: "เกตเวย์ API (API Gateway)", keys: ["api"] },
  { name: "เอเจนต์หลักและระบบ RAG", keys: ["agent", "rag"] },
  { name: "บริการข้อมูลสภาพอากาศ", keys: ["weather"] },
  { name: "บริการข้อมูลการเดินทางและจราจร", keys: ["transport", "traffic"] },
  { name: "ระบบแจ้งเตือนภัยพิบัติ", keys: ["disaster"] },
  { name: "เอ็นจินตัดสินใจและโมเดลความเสี่ยง", keys: ["decision_engine", "risk_model"] },
];

const STATE_LABEL: Record<ComponentState, string> = {
  operational: "พร้อมใช้งานปกติ",
  degraded: "ประสิทธิภาพลดลง",
  down: "ไม่พร้อมใช้งาน",
  unknown: "ไม่ทราบสถานะ",
};

const TAB_SHORT_LABELS: Record<TabId, string> = {
  overview: "ภาพรวม",
  jobs: "คิวงาน",
  reviews: "ตรวจทาน",
  audit: "บันทึก",
  exports: "ส่งออก",
};

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const queryClient = useQueryClient();

  const jobs = useQuery({
    queryKey: ["admin", "jobs", "overview"],
    queryFn: ({ signal }) => api.getAdminJobs({ limit: 5 }, signal),
    retry: false,
  });

  const reviews = useQuery({
    queryKey: ["admin", "reviews", "overview"],
    queryFn: ({ signal }) => api.getFeedbackReviews({ status: "pending", limit: 5 }, signal),
    retry: false,
  });

  const audit = useQuery({
    queryKey: ["admin", "audit-logs", "overview"],
    queryFn: ({ signal }) => api.getAuditLogs({ limit: 5 }, signal),
    retry: false,
  });

  const serviceStatus = useQuery({
    queryKey: ["service-status"],
    queryFn: ({ signal }) => fetchServiceStatus(signal),
    refetchInterval: 30_000,
  });

  const handleTokenChange = () => {
    queryClient.invalidateQueries({ queryKey: ["admin"] });
    queryClient.invalidateQueries({ queryKey: ["service-status"] });
  };

  const serviceCards = SERVICE_CARD_CONFIG.map((config, index) => {
    const component = serviceStatus.data?.components.find((candidate) =>
      config.keys.includes(candidate.key),
    );
    const state =
      component?.state ??
      (index === 0 && serviceStatus.isError ? "down" : "unknown");
    return {
      ...config,
      state,
      status: STATE_LABEL[state],
      detail:
        component?.message ??
        (serviceStatus.isError
          ? index === 0
            ? "ไม่สามารถเชื่อมต่อปลายทาง API Status ได้"
            : "ไม่สามารถตรวจสอบคอมโพเนนต์ย่อยได้"
          : "สตรีมข้อมูลสถานะการทำงานจริง"),
    };
  });

  const overallState = serviceStatus.isError
    ? "down"
    : (serviceStatus.data?.overall ?? "unknown");
  const overallLabel = serviceStatus.isPending
    ? "กำลังตรวจสอบระบบหลัก…"
    : overallState === "operational"
      ? "ระบบหลักทั้งหมดทำงานปกติ"
      : overallState === "degraded"
        ? "บางระบบมีประสิทธิภาพลดลง"
        : overallState === "down"
          ? "ระบบไม่พร้อมให้บริการ"
          : "ไม่ทราบสถานะระบบหลัก";

  return (
    <main className="min-h-screen bg-[#f8fbff] text-ink">
      {/* Sidebar Navigation */}
      <aside className="fixed inset-y-0 hidden w-64 flex-col bg-ink p-6 text-white lg:flex">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold">
          <Gauge /> WayPoint{" "}
          <span className="rounded bg-aqua px-1.5 py-0.5 text-[10px] tracking-widest">
            ADMIN
          </span>
        </Link>

        <nav className="mt-12 space-y-2 text-sm">
          <Nav
            icon={<Gauge size={17} />}
            label="ภาพรวมระบบ"
            active={activeTab === "overview"}
            onClick={() => setActiveTab("overview")}
          />
          <Nav
            icon={<Activity size={17} />}
            label="คิวงานและไปป์ไลน์"
            active={activeTab === "jobs"}
            onClick={() => setActiveTab("jobs")}
          />
          <Nav
            icon={<Users size={17} />}
            label="ตรวจทานความปลอดภัย"
            active={activeTab === "reviews"}
            onClick={() => setActiveTab("reviews")}
          />
          <Nav
            icon={<Database size={17} />}
            label="บันทึกการตรวจสอบสิทธิ์"
            active={activeTab === "audit"}
            onClick={() => setActiveTab("audit")}
          />
          <Nav
            icon={<FileDown size={17} />}
            label="ส่งออกชุดข้อมูลฝึกสอน"
            active={activeTab === "exports"}
            onClick={() => setActiveTab("exports")}
          />
        </nav>

        <div className="mt-auto rounded-xl border border-white/15 p-4 text-xs text-white/65">
          <span className="flex items-center gap-2 font-bold text-white">
            <CheckCircle2 size={15} className="text-[#b9e5fb]" /> ความมั่นคงและปลอดภัยของระบบ
          </span>
          <p className="mt-2 leading-relaxed">
            การวินิจฉัยจะไม่เปิดเผยตำแหน่งส่วนบุคคล คำค้นหาเฉพาะ หรือข้อมูลระบุตัวตนของผู้ใช้
          </p>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="lg:pl-64">
        <header className="flex items-center justify-between border-b border-ink/10 bg-white px-6 py-5 sm:px-10">
          <div>
            <p className="text-xs font-bold tracking-[.18em] text-aqua">
              ห้องควบคุมส่วนกลาง
            </p>
            <h1 className="mt-1 font-display text-2xl sm:text-3xl">
              {activeTab === "overview" && "สถานะระบบและการควบคุมส่วนกลาง"}
              {activeTab === "jobs" && "คิวงานประมวลผลไปป์ไลน์"}
              {activeTab === "reviews" && "คิวตรวจทานรายงานความปลอดภัย"}
              {activeTab === "audit" && "บันทึกประวัติการตรวจสอบความปลอดภัย"}
              {activeTab === "exports" && "ส่งออกชุดข้อมูลสำหรับฝึกสอนโมเดล"}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {/* Mobile Tab Selector */}
            <div className="flex rounded-xl border border-slate-200 bg-white p-1 text-xs lg:hidden">
              {(["overview", "jobs", "reviews", "audit", "exports"] as const).map(
                (tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`rounded-lg px-2.5 py-1 font-bold ${
                      activeTab === tab
                        ? "bg-slate-900 text-white"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {TAB_SHORT_LABELS[tab]}
                  </button>
                ),
              )}
            </div>

            <Link
              href="/"
              className="rounded-full border border-ink/15 px-4 py-2 text-xs font-bold transition hover:bg-slate-50"
            >
              แอปหลัก <ArrowUpRight className="ml-1 inline" size={14} />
            </Link>
            <UserNav />
          </div>
        </header>

        <div className="mx-auto max-w-7xl p-6 sm:p-10">
          {/* Admin Auth Bar */}
          <AdminAuthBar onTokenChange={handleTokenChange} />

          {/* TAB 1: OVERVIEW */}
          {activeTab === "overview" && (
            <div className="space-y-8">
              {/* System Pulse Section */}
              <section>
                <div className="flex items-end justify-between">
                  <div>
                    <h2 className="font-display text-2xl sm:text-3xl">สถานะความพร้อมของระบบ</h2>
                    <p className="mt-1 text-sm text-slate-500">
                      ความพร้อมในการให้บริการของคอมโพเนนต์ต่างๆ ในไปป์ไลน์การตัดสินใจแบบเรียลไทม์
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1.5 text-xs font-bold ${
                      overallState === "operational"
                        ? "bg-emerald-50 text-emerald-800"
                        : overallState === "degraded"
                          ? "bg-amber-50 text-amber-800"
                          : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {overallLabel}
                  </span>
                </div>

                <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {serviceCards.map(({ name, status, detail, state }) => {
                    const Icon =
                      state === "operational"
                        ? CheckCircle2
                        : state === "degraded"
                          ? CircleAlert
                          : state === "down"
                            ? XCircle
                            : CircleHelp;
                    const stateClass =
                      state === "operational"
                        ? "bg-emerald-50 text-emerald-700"
                        : state === "degraded"
                          ? "bg-amber-50 text-amber-700"
                          : state === "down"
                            ? "bg-red-50 text-red-700"
                            : "bg-slate-100 text-slate-600";
                    return (
                      <article
                        key={name}
                        className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm"
                      >
                        <div className="flex items-center justify-between">
                          <span className={`rounded-lg p-2 ${stateClass}`}>
                            <Icon size={18} aria-hidden />
                          </span>
                          <span className="text-[10px] font-bold tracking-wider text-slate-400">
                            ข้อมูลระบบ
                          </span>
                        </div>
                        <h3 className="mt-5 text-sm font-bold text-slate-900">{name}</h3>
                        <p className={`mt-1 text-sm font-bold ${stateClass.split(" ")[1]}`}>
                          {status}
                        </p>
                        <p className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-500">
                          {detail}
                        </p>
                      </article>
                    );
                  })}
                </div>
              </section>

              {/* Jobs and Safety Review Summary */}
              <section className="grid gap-6 xl:grid-cols-[1.35fr_.65fr]">
                <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-bold tracking-widest text-aqua">
                        ไปป์ไลน์อะซิงโครนัส
                      </p>
                      <h2 className="mt-1 font-display text-2xl">งานประมวลผลล่าสุด</h2>
                    </div>
                    <button
                      type="button"
                      onClick={() => setActiveTab("jobs")}
                      className="text-xs font-bold text-pine hover:underline"
                    >
                      ดูทั้งหมด <ArrowUpRight className="inline" size={14} />
                    </button>
                  </div>

                  <div className="mt-6 overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b border-slate-100 text-[11px] uppercase tracking-wider text-slate-400">
                        <tr>
                          <th className="pb-3 font-bold">รหัสงาน (JOB ID)</th>
                          <th className="pb-3 font-bold">ประเภทงาน</th>
                          <th className="pb-3 font-bold">สถานะ</th>
                          <th className="pb-3 font-bold">ขั้นตอน</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {jobs.isLoading ? (
                          <tr>
                            <td colSpan={4} className="py-8 text-center text-slate-400">
                              กำลังโหลดข้อมูลงาน...
                            </td>
                          </tr>
                        ) : jobs.isError ? (
                          <tr>
                            <td colSpan={4} className="py-8 text-center text-slate-400">
                              กรุณาเชื่อมต่อโทเค็นผู้ดูแลระบบด้านบนเพื่อดูข้อมูลงานสด
                            </td>
                          </tr>
                        ) : !jobs.data?.items || jobs.data.items.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="py-8 text-center text-slate-400">
                              ไม่พบประวัติงานล่าสุด
                            </td>
                          </tr>
                        ) : (
                          jobs.data.items.slice(0, 5).map((job) => (
                            <tr key={job.job_id} className="hover:bg-slate-50">
                              <td className="py-3 font-mono text-slate-700">
                                {job.job_id.slice(0, 8)}...
                              </td>
                              <td className="py-3 font-bold text-slate-800">{job.type}</td>
                              <td className="py-3">
                                <span
                                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                                    job.status === "succeeded"
                                      ? "bg-emerald-50 text-emerald-700"
                                      : job.status === "running"
                                        ? "bg-sky-50 text-sky-700"
                                        : job.status === "failed"
                                          ? "bg-red-50 text-red-700"
                                          : "bg-slate-100 text-slate-700"
                                  }`}
                                >
                                  {job.status === "succeeded"
                                    ? "สำเร็จ"
                                    : job.status === "running"
                                      ? "กำลังทำงาน"
                                      : job.status === "failed"
                                        ? "ล้มเหลว"
                                        : job.status === "queued"
                                          ? "รอคิว"
                                          : job.status}
                                </span>
                              </td>
                              <td className="py-3 font-mono text-slate-500">{job.stage}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  <p className="mt-5 rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-500">
                    <ShieldAlert className="mr-1 inline text-aqua" size={15} /> การประเมินแบบเรียลไทม์ส่งผ่านสตรีม Server-Sent Events (SSE) พร้อมระบบตั๋วความปลอดภัย
                  </p>
                </article>

                <article className="rounded-2xl bg-pine p-6 text-white shadow-sm">
                  <p className="text-xs font-bold tracking-widest text-[#b9e5fb]">
                    การตรวจสอบโดยผู้เชี่ยวชาญ
                  </p>
                  <h2 className="mt-2 font-display text-3xl">ตรวจทานความปลอดภัย</h2>
                  <p className="mt-3 text-sm leading-relaxed text-white/70">
                    ตรวจสอบรายงานความปลอดภัยและข้อเสนอแนะความแม่นยำของเส้นทางจากผู้ใช้
                  </p>

                  <div className="mt-8 rounded-xl bg-white/10 p-5">
                    <div className="flex items-baseline gap-2">
                      <span className="font-display text-4xl font-bold">
                        {reviews.data?.items ? reviews.data.items.length : "0"}
                      </span>
                      <span className="text-sm text-white/70">รายการที่รอในคิวตรวจทาน</span>
                    </div>
                    <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/15">
                      <div
                        className="h-full rounded-full bg-[#b9e5fb]"
                        style={{
                          width: `${Math.min(
                            ((reviews.data?.items.length ?? 0) / 10) * 100,
                            100,
                          )}%`,
                        }}
                      />
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setActiveTab("reviews")}
                    className="mt-6 w-full rounded-xl bg-white px-4 py-3 text-sm font-bold text-pine transition hover:bg-slate-100"
                  >
                    เปิดคิวตรวจทานความปลอดภัย
                  </button>
                </article>
              </section>

              {/* Quick Metrics */}
              <section className="grid gap-4 md:grid-cols-4">
                <MiniStat
                  label="งานที่สำเร็จ"
                  value={jobs.data?.items ? String(jobs.data.items.length) : "—"}
                  change={jobs.isError ? "ต้องยืนยันตัวตน" : "สดจากฐานข้อมูล"}
                />
                <MiniStat
                  label="ข้อเสนอแนะรอตรวจ"
                  value={reviews.data?.items ? String(reviews.data.items.length) : "—"}
                  change="รอการตัดสินใจของผู้ตรวจ"
                />
                <MiniStat
                  label="บันทึกการตรวจสอบ"
                  value={audit.data?.items ? String(audit.data.items.length) : "—"}
                  change="ประวัติความปลอดภัยถาวร"
                />
                <MiniStat
                  label="สถานะแกนระบบหลัก"
                  value={overallState === "operational" ? "100%" : "ประสิทธิภาพลดลง"}
                  change="สถานะความสมบูรณ์สด"
                />
              </section>
            </div>
          )}

          {/* TAB 2: JOBS */}
          {activeTab === "jobs" && <AdminJobsTab />}

          {/* TAB 3: REVIEWS */}
          {activeTab === "reviews" && <AdminReviewsTab />}

          {/* TAB 4: AUDIT LOGS */}
          {activeTab === "audit" && <AdminAuditTab />}

          {/* TAB 5: DATA EXPORTS */}
          {activeTab === "exports" && <AdminExportsTab />}
        </div>
      </div>
    </main>
  );
}

function Nav({
  icon,
  label,
  active = false,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-3 rounded-xl px-3.5 py-3 text-left transition ${
        active
          ? "bg-white/12 font-bold text-white shadow-sm"
          : "text-white/60 hover:bg-white/5 hover:text-white"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function MiniStat({
  label,
  value,
  change,
}: {
  label: string;
  value: string;
  change: string;
}) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-bold tracking-wider text-slate-400">
        {label}
      </p>
      <div className="mt-3 flex items-end justify-between">
        <b className="font-display text-3xl text-slate-900">{value}</b>
        <span className="text-xs font-bold text-pine">{change}</span>
      </div>
    </article>
  );
}
