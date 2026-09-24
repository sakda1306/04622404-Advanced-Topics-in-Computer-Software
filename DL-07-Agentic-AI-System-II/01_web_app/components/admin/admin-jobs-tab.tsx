"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Filter,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { AdminJob, JobStatus } from "@/lib/types";
import { AdminDiagnosticsModal } from "./admin-diagnostics-modal";

export function AdminJobsTab() {
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [selectedRecId, setSelectedRecId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const jobsQuery = useQuery({
    queryKey: ["admin", "jobs", statusFilter],
    queryFn: ({ signal }) =>
      api.getAdminJobs(
        statusFilter === "ALL" ? undefined : { status: statusFilter.toLowerCase() },
        signal,
      ),
    refetchInterval: 10_000,
  });

  const handleCopy = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const getStatusBadge = (status: JobStatus) => {
    switch (status) {
      case "succeeded":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-bold text-emerald-700">
            <CheckCircle2 size={12} /> สำเร็จ
          </span>
        );
      case "running":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2.5 py-0.5 text-xs font-bold text-sky-700">
            <Loader2 size={12} className="animate-spin" /> กำลังทำงาน
          </span>
        );
      case "queued":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-bold text-amber-700">
            <Clock size={12} /> รอคิว
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-bold text-red-700">
            <XCircle size={12} /> ล้มเหลว
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-slate-700">
            {status}
          </span>
        );
    }
  };

  const FILTER_OPTIONS = [
    { key: "ALL", label: "ทั้งหมด" },
    { key: "SUCCEEDED", label: "สำเร็จ" },
    { key: "RUNNING", label: "กำลังทำงาน" },
    { key: "QUEUED", label: "รอคิว" },
    { key: "FAILED", label: "ล้มเหลว" },
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl text-slate-900">งานประมวลผลอะซิงโครนัสและไปป์ไลน์</h2>
          <p className="mt-1 text-xs text-slate-500">
            วงจรชีวิตของงานประมวลผลและการทำงานของเอเจนต์เบื้องหลังแบบเรียลไทม์
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white p-1 text-xs">
            <Filter size={14} className="ml-2 text-slate-400" />
            {FILTER_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => setStatusFilter(opt.key)}
                className={`rounded-lg px-2.5 py-1 font-bold transition ${
                  statusFilter === opt.key
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => jobsQuery.refetch()}
            disabled={jobsQuery.isFetching}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw
              size={13}
              className={jobsQuery.isFetching ? "animate-spin text-pine" : ""}
            />
            รีเฟรช
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50/50 text-[11px] uppercase tracking-wider text-slate-400">
              <tr>
                <th className="px-5 py-3.5 font-bold">รหัสงาน (Job ID)</th>
                <th className="px-5 py-3.5 font-bold">ประเภทงาน</th>
                <th className="px-5 py-3.5 font-bold">สถานะ</th>
                <th className="px-5 py-3.5 font-bold">ขั้นตอน</th>
                <th className="px-5 py-3.5 font-bold">รอบที่ลอง</th>
                <th className="px-5 py-3.5 font-bold">สร้างเมื่อ</th>
                <th className="px-5 py-3.5 font-bold text-right">การวินิจฉัย</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {jobsQuery.isLoading ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-slate-400">
                    <Loader2 size={24} className="mx-auto mb-2 animate-spin text-pine" />
                    กำลังโหลดข้อมูลงานจาก API...
                  </td>
                </tr>
              ) : jobsQuery.isError ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-red-500">
                    <AlertCircle size={24} className="mx-auto mb-2 text-red-400" />
                    ไม่สามารถดึงข้อมูลงานได้: กรุณาตรวจสอบโทเค็นหรือการเชื่อมต่อเครือข่าย
                  </td>
                </tr>
              ) : !jobsQuery.data?.items || jobsQuery.data.items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-slate-400">
                    ไม่พบงานที่ตรงกับตัวกรองปัจจุบัน
                  </td>
                </tr>
              ) : (
                jobsQuery.data.items.map((job: AdminJob) => (
                  <tr key={job.job_id} className="hover:bg-slate-50/80">
                    <td className="px-5 py-3.5 font-mono text-slate-700">
                      <div className="flex items-center gap-1.5">
                        <span>{job.job_id.slice(0, 8)}...</span>
                        <button
                          type="button"
                          onClick={() => handleCopy(job.job_id)}
                          className="text-slate-400 hover:text-slate-700"
                          title="คัดลอก UUID ทั้งหมด"
                        >
                          <Copy size={12} />
                        </button>
                        {copiedId === job.job_id && (
                          <span className="text-[10px] text-emerald-600 font-bold">คัดลอกแล้ว</span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3.5 font-bold text-slate-800">
                      {job.type}
                    </td>
                    <td className="px-5 py-3.5">{getStatusBadge(job.status)}</td>
                    <td className="px-5 py-3.5 font-mono text-slate-600">
                      {job.stage}
                    </td>
                    <td className="px-5 py-3.5 font-bold text-slate-700">
                      #{job.attempts}
                    </td>
                    <td className="px-5 py-3.5 text-slate-500">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {job.recommendation_id ? (
                        <button
                          type="button"
                          onClick={() => setSelectedRecId(job.recommendation_id)}
                          className="inline-flex items-center gap-1 rounded-lg bg-pine/10 px-2.5 py-1 text-xs font-bold text-pine hover:bg-pine/20"
                        >
                          วินิจฉัย <ExternalLink size={11} />
                        </button>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Diagnostics Details Modal */}
      <AdminDiagnosticsModal
        recommendationId={selectedRecId}
        onClose={() => setSelectedRecId(null)}
      />
    </div>
  );
}
