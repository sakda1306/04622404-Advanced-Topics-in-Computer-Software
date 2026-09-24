"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Filter,
  Loader2,
  MessageSquare,
  RefreshCw,
  Star,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { ReviewDecision, ReviewQueueItem, ReviewStatus } from "@/lib/types";

export function AdminReviewsTab() {
  const [statusFilter, setStatusFilter] = useState<ReviewStatus>("pending");
  const [activeReviewItem, setActiveReviewItem] = useState<{
    item: ReviewQueueItem;
    decision: ReviewDecision;
  } | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const queryClient = useQueryClient();

  const reviewsQuery = useQuery({
    queryKey: ["admin", "reviews", statusFilter],
    queryFn: ({ signal }) =>
      api.getFeedbackReviews({ status: statusFilter }, signal),
    refetchInterval: 15_000,
  });

  const mutation = useMutation({
    mutationFn: ({
      feedbackId,
      decision,
      note,
    }: {
      feedbackId: string;
      decision: ReviewDecision;
      note: string;
    }) => api.reviewFeedback(feedbackId, { status: decision, note }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "reviews"] });
      setActiveReviewItem(null);
      setReviewNote("");
    },
  });

  const handleOpenReview = (item: ReviewQueueItem, decision: ReviewDecision) => {
    setActiveReviewItem({ item, decision });
    setReviewNote("");
  };

  const handleConfirmReview = () => {
    if (!activeReviewItem) return;
    mutation.mutate({
      feedbackId: activeReviewItem.item.feedback_id,
      decision: activeReviewItem.decision,
      note: reviewNote.trim() || undefined,
    });
  };

  const FILTER_OPTIONS: { key: ReviewStatus; label: string }[] = [
    { key: "pending", label: "รอตรวจทาน" },
    { key: "approved", label: "อนุมัติแล้ว" },
    { key: "rejected", label: "ปฏิเสธแล้ว" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl text-slate-900">คิวตรวจทานรายงานความปลอดภัย</h2>
          <p className="mt-1 text-xs text-slate-500">
            ตรวจสอบข้อเสนอแนะความปลอดภัย รายงานความคลาดเคลื่อน และสัญญาณเตือนจากผู้ใช้
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
            onClick={() => reviewsQuery.refetch()}
            disabled={reviewsQuery.isFetching}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw
              size={13}
              className={reviewsQuery.isFetching ? "animate-spin text-pine" : ""}
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
                <th className="px-5 py-3.5 font-bold">รหัสข้อเสนอแนะ (Feedback ID)</th>
                <th className="px-5 py-3.5 font-bold">คะแนน / สัญญาณ</th>
                <th className="px-5 py-3.5 font-bold">ประเภทรายงาน</th>
                <th className="px-5 py-3.5 font-bold">ความคิดเห็นของผู้ใช้</th>
                <th className="px-5 py-3.5 font-bold">ส่งเมื่อ</th>
                <th className="px-5 py-3.5 font-bold text-right">การจัดการ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {reviewsQuery.isLoading ? (
                <tr>
                  <td colSpan={6} className="py-16 text-center text-slate-400">
                    <Loader2 size={24} className="mx-auto mb-2 animate-spin text-pine" />
                    กำลังโหลดคิวตรวจทาน...
                  </td>
                </tr>
              ) : reviewsQuery.isError ? (
                <tr>
                  <td colSpan={6} className="py-16 text-center text-red-500">
                    <AlertCircle size={24} className="mx-auto mb-2 text-red-400" />
                    ไม่สามารถดึงข้อมูลคิวตรวจทานได้: กรุณาตรวจสอบว่าโทเค็นมีสิทธิ์ safety:review หรือไม่
                  </td>
                </tr>
              ) : !reviewsQuery.data?.items || reviewsQuery.data.items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-16 text-center text-slate-400">
                    ไม่พบรายการข้อเสนอแนะในสถานะนี้
                  </td>
                </tr>
              ) : (
                reviewsQuery.data.items.map((item: ReviewQueueItem) => (
                  <tr key={item.feedback_id} className="hover:bg-slate-50/80">
                    <td className="px-5 py-3.5 font-mono text-slate-700">
                      {item.feedback_id.slice(0, 8)}...
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        {item.rating && (
                          <span className="flex items-center gap-1 font-bold text-amber-600">
                            <Star size={13} className="fill-amber-500 text-amber-500" />
                            {item.rating}/5
                          </span>
                        )}
                        {item.helpful !== null && (
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                              item.helpful
                                ? "bg-emerald-50 text-emerald-700"
                                : "bg-red-50 text-red-700"
                            }`}
                          >
                            {item.helpful ? (
                              <ThumbsUp size={10} />
                            ) : (
                              <ThumbsDown size={10} />
                            )}
                            {item.helpful ? "มีประโยชน์" : "ไม่มีประโยชน์"}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      {item.report_type ? (
                        <span className="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-bold text-red-700">
                          {item.report_type}
                        </span>
                      ) : (
                        <span className="text-slate-400">ข้อเสนอแนะทั่วไป</span>
                      )}
                    </td>
                    <td className="max-w-xs truncate px-5 py-3.5 text-slate-700">
                      {item.comment || <span className="text-slate-300">ไม่มีข้อคิดเห็นเพิ่มเติม</span>}
                    </td>
                    <td className="px-5 py-3.5 text-slate-500">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {item.review_status === "pending" ? (
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleOpenReview(item, "approved")}
                            className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700 hover:bg-emerald-100"
                          >
                            <CheckCircle2 size={12} /> อนุมัติ
                          </button>
                          <button
                            type="button"
                            onClick={() => handleOpenReview(item, "rejected")}
                            className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-2.5 py-1 text-xs font-bold text-red-700 hover:bg-red-100"
                          >
                            <XCircle size={12} /> ปฏิเสธ
                          </button>
                        </div>
                      ) : (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                            item.review_status === "approved"
                              ? "bg-emerald-50 text-emerald-700"
                              : "bg-red-50 text-red-700"
                          }`}
                        >
                          {item.review_status === "approved" ? "อนุมัติแล้ว" : "ปฏิเสธแล้ว"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Review Modal Dialog */}
      {activeReviewItem && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
        >
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl">
            <div className="flex items-center gap-2">
              <MessageSquare size={20} className="text-pine" />
              <h3 className="font-display text-xl text-slate-900">
                ยืนยัน{activeReviewItem.decision === "approved" ? "การอนุมัติ" : "การปฏิเสธ"}
              </h3>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              รหัสข้อเสนอแนะ:{" "}
              <span className="font-mono text-slate-700">
                {activeReviewItem.item.feedback_id}
              </span>
            </p>

            {activeReviewItem.item.comment && (
              <div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs italic text-slate-600">
                &ldquo;{activeReviewItem.item.comment}&rdquo;
              </div>
            )}

            <div className="mt-4">
              <label className="block text-xs font-bold text-slate-700">
                บันทึกของผู้ตรวจทาน (ไม่บังคับ)
              </label>
              <textarea
                rows={3}
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
                placeholder="ระบุเหตุผลหรือมาตรการแก้ไขที่ดำเนินการ..."
                className="mt-1.5 w-full rounded-2xl border border-slate-200 p-3 text-xs focus:border-pine focus:outline-none"
              />
            </div>

            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setActiveReviewItem(null)}
                disabled={mutation.isPending}
                className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-50"
              >
                ยกเลิก
              </button>
              <button
                type="button"
                onClick={handleConfirmReview}
                disabled={mutation.isPending}
                className={`inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold text-white transition ${
                  activeReviewItem.decision === "approved"
                    ? "bg-emerald-600 hover:bg-emerald-700"
                    : "bg-red-600 hover:bg-red-700"
                }`}
              >
                {mutation.isPending && (
                  <Loader2 size={13} className="animate-spin" />
                )}
                ส่งผลการตัดสิน
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
