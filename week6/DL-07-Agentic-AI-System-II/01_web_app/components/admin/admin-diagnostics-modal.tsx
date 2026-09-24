"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  Copy,
  Cpu,
  Layers,
  Loader2,
  Shield,
  X,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";

interface AdminDiagnosticsModalProps {
  recommendationId: string | null;
  onClose: () => void;
}

export function AdminDiagnosticsModal({
  recommendationId,
  onClose,
}: AdminDiagnosticsModalProps) {
  const [copied, setCopied] = useState(false);

  const query = useQuery({
    queryKey: ["admin", "recommendation", recommendationId],
    queryFn: ({ signal }) =>
      recommendationId
        ? api.getAdminRecommendation(recommendationId, signal)
        : Promise.reject(new Error("No ID")),
    enabled: Boolean(recommendationId),
    retry: false,
  });

  if (!recommendationId) return null;

  const data = query.data;

  const handleCopy = () => {
    if (recommendationId) {
      navigator.clipboard.writeText(recommendationId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
    >
      <div className="relative max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl sm:p-8">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-5 top-5 rounded-full p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          aria-label="ปิดหน้าต่าง"
        >
          <X size={20} />
        </button>

        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-pine">
            <Shield size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display text-2xl text-slate-900">
                การวินิจฉัยคำแนะนำและผลการตัดสินใจ
              </h2>
              {data?.risk_level && (
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                    data.risk_level === "HIGH"
                      ? "bg-red-100 text-red-800"
                      : data.risk_level === "MEDIUM"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-emerald-100 text-emerald-800"
                  }`}
                >
                  {data.risk_level === "HIGH"
                    ? "ความเสี่ยงสูง (HIGH)"
                    : data.risk_level === "MEDIUM"
                      ? "ความเสี่ยงปานกลาง (MEDIUM)"
                      : "ความเสี่ยงต่ำ (LOW)"}
                </span>
              )}
              {data?.recommendation_type && (
                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-slate-700">
                  {data.recommendation_type}
                </span>
              )}
            </div>
            <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
              <span className="font-mono">{recommendationId}</span>
              <button
                type="button"
                onClick={handleCopy}
                className="inline-flex items-center gap-1 text-pine hover:underline"
              >
                <Copy size={12} /> {copied ? "คัดลอกแล้ว" : "คัดลอก"}
              </button>
            </div>
          </div>
        </div>

        {query.isLoading && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 size={32} className="animate-spin text-pine" />
            <p className="mt-3 text-sm text-slate-500">
              กำลังโหลดข้อมูลบันทึกการวินิจฉัย...
            </p>
          </div>
        )}

        {query.isError && (
          <div className="my-8 rounded-2xl bg-red-50 p-6 text-center text-sm text-red-700">
            <AlertTriangle size={32} className="mx-auto mb-2 text-red-500" />
            <p className="font-bold">ไม่สามารถโหลดข้อมูลการวินิจฉัยได้</p>
            <p className="mt-1 text-xs text-red-600">
              {query.error instanceof Error
                ? query.error.message
                : "กรุณาตรวจสอบสิทธิ์การเข้าถึงและโทเค็นของคุณ"}
            </p>
          </div>
        )}

        {data && (
          <div className="mt-6 space-y-6">
            {/* Quick stats grid */}
            <div className="grid gap-3 sm:grid-cols-4">
              <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                <span className="text-xs text-slate-400">คะแนนความเสี่ยง</span>
                <p className="mt-1 font-display text-2xl font-bold text-slate-800">
                  {data.risk_score !== null ? data.risk_score.toFixed(2) : "—"}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                <span className="text-xs text-slate-400">ระดับความมั่นใจ</span>
                <p className="mt-1 font-display text-2xl font-bold text-slate-800">
                  {data.risk_confidence !== null
                    ? `${Math.round(data.risk_confidence * 100)}%`
                    : "—"}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                <span className="text-xs text-slate-400">ความสดใหม่ข้อมูล</span>
                <p className="mt-1 font-display text-xl font-bold text-slate-800">
                  {data.overall_is_stale ? (
                    <span className="text-amber-600">ข้อมูลเก่า</span>
                  ) : (
                    <span className="text-emerald-600">สดใหม่</span>
                  )}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                <span className="text-xs text-slate-400">เสร็จสิ้นเมื่อ</span>
                <p className="mt-1 text-xs font-bold text-slate-800">
                  {data.completed_at
                    ? new Date(data.completed_at).toLocaleTimeString()
                    : "กำลังประมวลผล"}
                </p>
              </div>
            </div>

            {/* Versions snapshot */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <Layers size={16} className="text-pine" /> เวอร์ชันระบบและโมเดล
              </h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-4 text-xs">
                {Object.entries(data.versions ?? {}).map(([key, val]) => (
                  <div key={key} className="rounded-xl bg-slate-50 p-2.5">
                    <span className="uppercase tracking-wider text-slate-400">
                      {key}
                    </span>
                    <p className="mt-0.5 font-mono font-bold text-slate-800">
                      {val ?? "n/a"}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* Data Freshness */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <Clock size={16} className="text-pine" /> ความสดใหม่ของชุดข้อมูลอ้างอิง
              </h3>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-100 text-slate-400">
                    <tr>
                      <th className="pb-2 font-bold">หมวดหมู่ข้อมูล</th>
                      <th className="pb-2 font-bold">อัปเดตล่าสุด</th>
                      <th className="pb-2 font-bold">อายุข้อมูล (วินาที)</th>
                      <th className="pb-2 font-bold">สถานะ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(data.data_freshness ?? []).map((item, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="py-2.5 font-bold text-slate-800">
                          {item.category}
                        </td>
                        <td className="py-2.5 text-slate-600">
                          {item.updated_at
                            ? new Date(item.updated_at).toLocaleString()
                            : "—"}
                        </td>
                        <td className="py-2.5 font-mono text-slate-600">
                          {item.age_seconds !== null ? `${item.age_seconds}s` : "—"}
                        </td>
                        <td className="py-2.5">
                          <span
                            className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                              item.is_stale
                                ? "bg-amber-100 text-amber-800"
                                : "bg-emerald-100 text-emerald-800"
                            }`}
                          >
                            {item.is_stale ? "ข้อมูลเก่า" : "สดใหม่"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Agent Runs */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <Bot size={16} className="text-pine" /> ประวัติรอบการทำงานของเอเจนต์ (
                {data.agent_runs?.length ?? 0})
              </h3>
              {data.agent_runs && data.agent_runs.length > 0 ? (
                <div className="mt-3 space-y-3">
                  {data.agent_runs.map((run) => (
                    <div
                      key={run.run_id}
                      className="rounded-xl border border-slate-100 bg-slate-50 p-4 text-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-slate-800">
                            รอบที่ #{run.attempt}
                          </span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                              run.status === "success"
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-red-100 text-red-800"
                            }`}
                          >
                            {run.status === "success" ? "สำเร็จ" : "ล้มเหลว"}
                          </span>
                        </div>
                        <span className="text-slate-400">
                          {new Date(run.started_at).toLocaleTimeString()}
                        </span>
                      </div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-4 text-slate-600">
                        <div>
                          <span className="text-slate-400">ระยะเวลา:</span>{" "}
                          <b className="font-mono text-slate-800">
                            {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(2)}s` : "—"}
                          </b>
                        </div>
                        <div>
                          <span className="text-slate-400">เรียกใช้เครื่องมือ:</span>{" "}
                          <b className="font-mono text-slate-800">
                            {run.tool_calls ?? 0}
                          </b>
                        </div>
                        <div>
                          <span className="text-slate-400">เวอร์ชันเอเจนต์:</span>{" "}
                          <span className="font-mono">{run.agent_version ?? "n/a"}</span>
                        </div>
                        <div>
                          <span className="text-slate-400">สถานะ HTTP:</span>{" "}
                          <span className="font-mono">{run.http_status ?? "—"}</span>
                        </div>
                      </div>
                      {run.trace_id && (
                        <div className="mt-2 text-[11px] text-slate-400">
                          รหัสติดตาม (Trace ID): <span className="font-mono text-slate-600">{run.trace_id}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-3 text-xs text-slate-400">
                  ไม่พบบันทึกรอบการทำงานของเอเจนต์สำหรับคำแนะนำนี้
                </p>
              )}
            </div>
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-slate-200 bg-slate-50 px-5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100"
          >
            ปิดหน้าต่าง
          </button>
        </div>
      </div>
    </div>
  );
}
