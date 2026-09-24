"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Database,
  Filter,
  Info,
  Loader2,
  RefreshCw,
  X,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { AuditLogItem, AuditResult } from "@/lib/types";

export function AdminAuditTab() {
  const [resultFilter, setResultFilter] = useState<string>("ALL");
  const [selectedItem, setSelectedItem] = useState<AuditLogItem | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["admin", "audit-logs", resultFilter],
    queryFn: ({ signal }) =>
      api.getAuditLogs(
        resultFilter === "ALL" ? undefined : { result: resultFilter.toLowerCase() },
        signal,
      ),
    refetchInterval: 20_000,
  });

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const getResultBadge = (result: AuditResult) => {
    switch (result) {
      case "success":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-bold text-emerald-700">
            <CheckCircle2 size={11} /> สำเร็จ
          </span>
        );
      case "denied":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-bold text-amber-700">
            <AlertCircle size={11} /> ถูกปฏิเสธ
          </span>
        );
      case "error":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-bold text-red-700">
            <XCircle size={11} /> ข้อผิดพลาด
          </span>
        );
      default:
        return (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-700">
            {result}
          </span>
        );
    }
  };

  const FILTER_OPTIONS = [
    { key: "ALL", label: "ทั้งหมด" },
    { key: "SUCCESS", label: "สำเร็จ" },
    { key: "DENIED", label: "ถูกปฏิเสธ" },
    { key: "ERROR", label: "ข้อผิดพลาด" },
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl text-slate-900">บันทึกประวัติการตรวจสอบและความปลอดภัย</h2>
          <p className="mt-1 text-xs text-slate-500">
            บันทึกความปลอดภัยที่ไม่สามารถแก้ไขได้ แสดงการกระทำของผู้ดูแล สิทธิ์ และการเข้าถึงข้อมูล
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white p-1 text-xs">
            <Filter size={14} className="ml-2 text-slate-400" />
            {FILTER_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => setResultFilter(opt.key)}
                className={`rounded-lg px-2.5 py-1 font-bold transition ${
                  resultFilter === opt.key
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
            onClick={() => auditQuery.refetch()}
            disabled={auditQuery.isFetching}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw
              size={13}
              className={auditQuery.isFetching ? "animate-spin text-pine" : ""}
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
                <th className="px-5 py-3.5 font-bold">รหัส / เวลา</th>
                <th className="px-5 py-3.5 font-bold">ประเภทผู้กระทำ</th>
                <th className="px-5 py-3.5 font-bold">การกระทำ</th>
                <th className="px-5 py-3.5 font-bold">เป้าหมาย</th>
                <th className="px-5 py-3.5 font-bold">ผลลัพธ์</th>
                <th className="px-5 py-3.5 font-bold">รหัสความสัมพันธ์ (Correlation ID)</th>
                <th className="px-5 py-3.5 font-bold text-right">ข้อมูลเพิ่มเติม</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {auditQuery.isLoading ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-slate-400">
                    <Loader2 size={24} className="mx-auto mb-2 animate-spin text-pine" />
                    กำลังโหลดบันทึกการตรวจสอบ...
                  </td>
                </tr>
              ) : auditQuery.isError ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-red-500">
                    <AlertCircle size={24} className="mx-auto mb-2 text-red-400" />
                    ไม่สามารถดึงข้อมูลบันทึกได้: กรุณาตรวจสอบว่าโทเค็นมีสิทธิ์ admin:read หรือไม่
                  </td>
                </tr>
              ) : !auditQuery.data?.items || auditQuery.data.items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-slate-400">
                    ไม่พบบันทึกการตรวจสอบที่ตรงกับตัวกรองที่เลือก
                  </td>
                </tr>
              ) : (
                auditQuery.data.items.map((log: AuditLogItem) => (
                  <tr key={log.id} className="hover:bg-slate-50/80">
                    <td className="px-5 py-3.5">
                      <div className="font-mono font-bold text-slate-800">#{log.id}</div>
                      <div className="text-[11px] text-slate-400">
                        {new Date(log.occurred_at).toLocaleString()}
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-mono font-bold text-slate-700">
                        {log.actor_type}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 font-mono font-bold text-slate-800">
                      {log.action}
                    </td>
                    <td className="px-5 py-3.5 text-slate-600">
                      {log.target_type ? (
                        <div className="space-y-0.5">
                          <span className="text-[10px] uppercase text-slate-400">
                            {log.target_type}:
                          </span>
                          <div className="truncate max-w-[120px] font-mono" title={log.target_id ?? ""}>
                            {log.target_id?.slice(0, 10)}...
                          </div>
                        </div>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">{getResultBadge(log.result)}</td>
                    <td className="px-5 py-3.5 font-mono text-slate-600">
                      <div className="flex items-center gap-1">
                        <span>{log.correlation_id.slice(0, 8)}...</span>
                        <button
                          type="button"
                          onClick={() => handleCopy(log.correlation_id)}
                          className="text-slate-400 hover:text-slate-700"
                        >
                          <Copy size={11} />
                        </button>
                        {copiedId === log.correlation_id && (
                          <span className="text-[9px] text-emerald-600 font-bold">✓</span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {log.metadata && Object.keys(log.metadata).length > 0 ? (
                        <button
                          type="button"
                          onClick={() => setSelectedItem(log)}
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-slate-600 hover:bg-slate-100"
                        >
                          <Info size={12} /> JSON
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

      {/* Metadata Detail Modal */}
      {selectedItem && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
        >
          <div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Database size={18} className="text-pine" />
                <h3 className="font-display text-lg text-slate-900">
                  ข้อมูลเมทาดาต้าการตรวจสอบ #{selectedItem.id}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedItem(null)}
                className="rounded-full p-1 text-slate-400 hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>
            <div className="mt-4">
              <pre className="max-h-72 overflow-y-auto rounded-xl bg-slate-900 p-4 text-xs font-mono text-emerald-400">
                {JSON.stringify(selectedItem.metadata, null, 2)}
              </pre>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedItem(null)}
                className="rounded-xl bg-slate-100 px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-200"
              >
                ปิด
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
