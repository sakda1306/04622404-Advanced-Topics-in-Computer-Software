"use client";

import { useMutation } from "@tanstack/react-query";
import {
  Calendar,
  CheckCircle2,
  Clock,
  Download,
  FileDown,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { TrainingExportResponse } from "@/lib/types";

export function AdminExportsTab() {
  const [rangeFrom, setRangeFrom] = useState<string>("");
  const [rangeTo, setRangeTo] = useState<string>("");
  const [activeExportId, setActiveExportId] = useState<string | null>(null);
  const [exportDetails, setExportDetails] = useState<TrainingExportResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const exportMutation = useMutation({
    mutationFn: (body: { from?: string; to?: string }) =>
      api.requestTrainingExport(body),
    onSuccess: async (data) => {
      setActiveExportId(data.export_id);
      setErrorMsg(null);
      // Immediately check status
      pollStatus(data.export_id);
    },
    onError: (err) => {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "ไม่สามารถส่งคำขอส่งออกชุดข้อมูลได้",
      );
    },
  });

  const pollStatus = async (id: string) => {
    setChecking(true);
    try {
      const result = await api.getTrainingExport(id);
      setExportDetails(result);
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "ไม่สามารถตรวจสอบสถานะการส่งออกได้",
      );
    } finally {
      setChecking(false);
    }
  };

  const handleRequestExport = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    exportMutation.mutate({
      from: rangeFrom ? new Date(rangeFrom).toISOString() : undefined,
      to: rangeTo ? new Date(rangeTo).toISOString() : undefined,
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-2xl text-slate-900">ส่งออกชุดข้อมูลสำหรับฝึกสอนโมเดล</h2>
        <p className="mt-1 text-xs text-slate-500">
          ส่งออกชุดข้อมูลที่ไม่ระบุตัวตนและเป็นไปตามนโยบายความเป็นส่วนตัวสำหรับการปรับแต่งโมเดลและการประเมินความปลอดภัย (FR-19, D-92)
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Export Request Form */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-pine/10 text-pine">
              <FileDown size={18} />
            </div>
            <div>
              <h3 className="font-display text-lg text-slate-900">ร้องขอส่งออกชุดข้อมูลใหม่</h3>
              <p className="text-xs text-slate-500">
                เลือกช่วงเวลาที่ต้องการ หรือส่งออกข้อมูลคำแนะนำทั้งหมดที่ประมวลผลเสร็จสิ้น
              </p>
            </div>
          </div>

          <form onSubmit={handleRequestExport} className="mt-6 space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-700">
                ตั้งแต่วันที่ / เวลา (ไม่บังคับ)
              </label>
              <div className="relative mt-1">
                <input
                  type="datetime-local"
                  value={rangeFrom}
                  onChange={(e) => setRangeFrom(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs focus:border-pine focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700">
                ถึงวันที่ / เวลา (ไม่บังคับ)
              </label>
              <div className="relative mt-1">
                <input
                  type="datetime-local"
                  value={rangeTo}
                  onChange={(e) => setRangeTo(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs focus:border-pine focus:outline-none"
                />
              </div>
            </div>

            <div className="rounded-xl bg-slate-50 p-3 text-xs leading-relaxed text-slate-500">
              <ShieldAlert className="mr-1 inline text-aqua" size={14} /> การรับประกันความเป็นส่วนตัว: สถานที่ส่วนตัว คำถามเฉพาะของผู้ใช้ และข้อมูลระบุตัวตนทั้งหมดจะถูกคัดกรองออกอย่างสมบูรณ์ก่อนบันทึกจัดเก็บ
            </div>

            {errorMsg && (
              <p className="text-xs font-bold text-red-600">{errorMsg}</p>
            )}

            <button
              type="submit"
              disabled={exportMutation.isPending}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-pine px-4 py-2.5 text-xs font-bold text-white transition hover:bg-pine/90 disabled:opacity-50"
            >
              {exportMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Sparkles size={14} className="text-[#b9e5fb]" />
              )}
              เข้าคิวงานส่งออกข้อมูล
            </button>
          </form>
        </div>

        {/* Export Status & Download Card */}
        <div className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h3 className="font-display text-lg text-slate-900">สถานะงานส่งออก</h3>
            {activeExportId && (
              <button
                type="button"
                onClick={() => pollStatus(activeExportId)}
                disabled={checking}
                className="inline-flex items-center gap-1 text-xs font-bold text-pine hover:underline"
              >
                <RefreshCw size={12} className={checking ? "animate-spin" : ""} /> ตรวจสอบสถานะ
              </button>
            )}
          </div>

          <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
            {exportDetails ? (
              <div className="w-full space-y-4 text-left">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">รหัสงานส่งออก</span>
                  <span className="font-mono text-xs font-bold text-slate-800">
                    {exportDetails.export_id.slice(0, 12)}...
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">สถานะ</span>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                      exportDetails.status === "completed"
                        ? "bg-emerald-100 text-emerald-800"
                        : exportDetails.status === "failed"
                          ? "bg-red-100 text-red-800"
                          : "bg-sky-100 text-sky-800"
                    }`}
                  >
                    {exportDetails.status === "completed"
                      ? "เสร็จสมบูรณ์"
                      : exportDetails.status === "failed"
                        ? "ล้มเหลว"
                        : "กำลังประมวลผล"}
                  </span>
                </div>

                {exportDetails.row_count !== null && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400">จำนวนแถวที่ส่งออก</span>
                    <span className="font-display text-lg font-bold text-slate-900">
                      {exportDetails.row_count.toLocaleString()} แถว
                    </span>
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">สร้างเมื่อ</span>
                  <span className="text-xs text-slate-600">
                    {new Date(exportDetails.created_at).toLocaleString()}
                  </span>
                </div>

                {exportDetails.download_url ? (
                  <a
                    href={exportDetails.download_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-xs font-bold text-white shadow-sm hover:bg-emerald-700"
                  >
                    <Download size={15} /> ดาวน์โหลดไฟล์ชุดข้อมูล (.jsonl / .tar)
                  </a>
                ) : (
                  <div className="mt-4 flex items-center justify-center gap-2 rounded-xl bg-slate-50 p-4 text-xs text-slate-500">
                    <Clock size={16} className="text-slate-400" />
                    <span>กำลังประมวลผลโดยเวิร์กเกอร์เบื้องหลัง... กรุณาตรวจสอบสถานะอีกครั้งในสักครู่</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-slate-400">
                <FileDown size={40} className="mx-auto mb-2 text-slate-300" />
                <p className="text-sm font-bold text-slate-600">ยังไม่มีงานส่งออกที่เลือก</p>
                <p className="mt-1 text-xs text-slate-400">
                  ส่งคำขอทางด้านซ้ายเพื่อติดตามความคืบหน้าและดาวน์โหลดไฟล์ที่นี่
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
