"use client";
import { useState } from "react";
import {
  AlertTriangle,
  Car,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Clock3,
  CloudRain,
  ExternalLink,
  Info,
  Lightbulb,
  LoaderCircle,
  MapPin,
  Navigation,
  Phone,
  Route,
  Send,
  ShieldAlert,
  ShieldCheck,
  Star,
  ThumbsDown,
  ThumbsUp,
  Timer,
  Waves,
  WifiOff,
} from "lucide-react";
import { useTrip } from "@/components/trip-context";
import { api } from "@/lib/api";
import type { DataCategory, DataFreshness, FeedbackCreate, Hazard, RiskFactor, RiskLevel } from "@/lib/types";

const RISK_UI: Record<RiskLevel, { label: string; icon: typeof ShieldCheck; className: string; bg: string; border: string }> = {
  LOW: {
    label: "ความเสี่ยงต่ำ (Low Risk)",
    icon: ShieldCheck,
    className: "text-[#b9e5fb]",
    bg: "bg-[#102e4e]",
    border: "border-sky-500/30",
  },
  MEDIUM: {
    label: "ความเสี่ยงปานกลาง (Medium Risk)",
    icon: ShieldAlert,
    className: "text-amber-300",
    bg: "bg-[#33250e]",
    border: "border-amber-500/30",
  },
  HIGH: {
    label: "ความเสี่ยงสูง (High Risk)",
    icon: AlertTriangle,
    className: "text-red-300",
    bg: "bg-[#381313]",
    border: "border-red-500/30",
  },
};

const ACTION_LABEL: Record<string, string> = {
  TRAVEL_NORMALLY: "เดินทางได้ตามปกติ",
  CHANGE_ROUTE: "ควรเปลี่ยนเส้นทาง",
  DELAY_TRAVEL: "ควรเลื่อนการเดินทาง",
  AVOID_TRAVEL: "ควรหลีกเลี่ยงการเดินทาง",
};

const CATEGORY_LABEL: Record<DataCategory, string> = {
  WEATHER: "สภาพอากาศ",
  TRANSPORT: "การจราจร / ขนส่ง",
  DISASTER: "ประกาศภัยพิบัติ",
  KNOWLEDGE_BASE: "คลังข้อมูลความรู้",
};

export function RecommendationDashboard() {
  const {
    status,
    recommendation,
    usingMock,
    errorMessage,
    progressMessage,
    selectedRouteIndex,
    setSelectedRouteIndex,
  } = useTrip();

  // Feedback State
  const [feedbackHelpful, setFeedbackHelpful] = useState<boolean | null>(null);
  const [feedbackRating, setFeedbackRating] = useState<number>(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

  if (status === "idle" || !recommendation) {
    return <IdleExample busy={status === "geocoding" || status === "submitting"} message={progressMessage} />;
  }

  const risk = recommendation.risk;
  const ui = risk?.level ? RISK_UI[risk.level] : {
    label: "ยังไม่มีระดับความเสี่ยง",
    icon: Info,
    className: "text-slate-200",
    bg: "bg-[#102e4e]",
    border: "border-slate-500/30",
  };
  const Icon = ui.icon;



  const primaryRoute = recommendation.routes?.primary;
  const alternatives = recommendation.routes?.alternatives ?? [];
  const allRoutes = [
    ...(primaryRoute ? [{ ...primaryRoute, isPrimary: true }] : []),
    ...alternatives.map((alt) => ({ ...alt, isPrimary: false })),
  ];
  const currentRoute = allRoutes[selectedRouteIndex] ?? primaryRoute;

  const handleSendFeedback = async () => {
    if (!recommendation.recommendation_id) return;
    setIsSubmittingFeedback(true);
    try {
      const payload: FeedbackCreate = {
        helpful: feedbackHelpful,
        rating: feedbackRating > 0 ? feedbackRating : undefined,
        comment: feedbackComment.trim() || undefined,
        outcome: feedbackHelpful ? "FOLLOWED" : "UNKNOWN",
      };
      await api.submitFeedback(recommendation.recommendation_id, payload);
      setFeedbackSubmitted(true);
    } catch {
      // Offline or mock fallback
      setFeedbackSubmitted(true);
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  return (
    <div className="space-y-6 text-left">
      {/* Demo / Offline notice */}
      {usingMock && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-xs text-amber-100">
          <WifiOff size={15} className="shrink-0" />
          <span>
            แสดงข้อมูลตัวอย่าง (โหมดออฟไลน์{errorMessage ? `: ${errorMessage}` : ""})
          </span>
        </div>
      )}

      {/* Row 1: Master Assessment & Live Signals */}
      <div className="grid gap-6 lg:grid-cols-[1.1fr_.9fr]">
        {/* Master Assessment Card */}
        <article className={`relative overflow-hidden rounded-2xl border ${ui.border} ${ui.bg} p-6 sm:p-8 shadow-float`}>
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold tracking-[.18em] text-white/60">
                  ASSESSMENT · {usingMock ? "DEMO DATA" : "VERIFIED PIPELINE"}
                </span>
                {recommendation.status && (
                  <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-bold text-white/80">
                    {recommendation.status.toUpperCase()}
                  </span>
                )}
              </div>
              <div className={`mt-5 flex items-center gap-3 ${ui.className}`}>
                <Icon size={28} />
                <span className="font-bold tracking-wide">{ui.label.toUpperCase()}</span>
              </div>
              <h3 className="mt-2 font-display text-4xl leading-tight sm:text-5xl">
                {ACTION_LABEL[recommendation.recommendation?.type ?? ""] ?? "รอผลการประเมิน"}
              </h3>
            </div>
            <span className="rounded-full bg-white/10 p-3 text-white">
              <Check size={20} />
            </span>
          </div>

          <p className="mt-6 max-w-lg text-sm leading-relaxed text-white/80">
            {recommendation.recommendation?.summary ?? "—"}
          </p>

          {/* Suggested Departure Time Highlight */}
          {recommendation.recommendation?.suggested_departure_time && (
            <div className="mt-5 flex items-center gap-3 rounded-xl border border-[#b9e5fb]/30 bg-[#0d2642] p-3.5 text-xs text-[#b9e5fb]">
              <Timer size={18} className="shrink-0 text-aqua" />
              <div>
                <b className="block text-white">เวลาออกเดินทางที่แนะนำ:</b>
                <span>{recommendation.recommendation.suggested_departure_time}</span>
              </div>
            </div>
          )}

          {/* Reasons list */}
          {recommendation.recommendation?.reasons && recommendation.recommendation.reasons.length > 0 && (
            <div className="mt-5 space-y-1.5">
              <p className="text-xs font-bold tracking-wider text-white/50">เหตุผลประกอบการตัดสินใจ:</p>
              <ul className="space-y-1 text-sm text-white/70">
                {recommendation.recommendation.reasons.map((reason) => (
                  <li key={reason} className="flex items-start gap-2">
                    <span className="mt-1 text-aqua" aria-hidden>•</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Metrics: Risk Score & Confidence */}
          <div className="mt-8 grid grid-cols-2 gap-4 border-t border-white/15 pt-5 text-sm">
            <div>
              <span className="text-xs text-white/50">Risk score (คะแนนความเสี่ยง)</span>
              {risk?.score != null ? (
                <div>
                  <b className="mt-1 block text-2xl font-bold">{Math.round(risk.score * 100)} / 100</b>
                  <div className="mt-2 h-1.5 w-full max-w-[140px] overflow-hidden rounded-full bg-white/15">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        risk.score > 0.6 ? "bg-red-400" : risk.score > 0.3 ? "bg-amber-400" : "bg-sky-400"
                      }`}
                      style={{ width: `${Math.min(100, Math.max(5, Math.round(risk.score * 100)))}%` }}
                    />
                  </div>
                </div>
              ) : (
                <div className="mt-1 flex items-center gap-1.5 text-xs text-amber-200/80">
                  <Info size={14} />
                  <span>รอข้อมูลเพิ่มเติม</span>
                </div>
              )}
            </div>

            <div>
              <span className="text-xs text-white/50">Confidence (ความเชื่อมั่น)</span>
              {risk?.confidence != null ? (
                <div>
                  <b className="mt-1 block text-2xl font-bold">{Math.round(risk.confidence * 100)}%</b>
                  <span className="text-xs text-white/60">
                    {risk.confidence >= 0.8 ? "สูง (High)" : risk.confidence >= 0.5 ? "ปานกลาง" : "ต่ำ"}
                  </span>
                </div>
              ) : (
                <div className="mt-1 flex items-center gap-1.5 text-xs text-white/60">
                  <Info size={14} />
                  <span>รอการประเมิน</span>
                </div>
              )}
            </div>
          </div>
        </article>

        {/* Live Signals & Evidence */}
        <EnvironmentSignalsSection
          factors={risk?.factors ?? []}
          hazards={recommendation.hazards ?? []}
          usingMock={usingMock}
          dataFreshness={recommendation.data_freshness}
          sourcesCount={recommendation.sources?.length ?? 0}
        />
      </div>

      {/* Row 2: Route Comparison & Legs Details */}
      {allRoutes.length > 0 && (
        <section className="rounded-2xl border border-white/15 bg-white/5 p-6 backdrop-blur">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div>
              <p className="text-xs font-bold tracking-[.18em] text-[#b9e5fb]">ROUTE PLANNING</p>
              <h3 className="mt-1 font-display text-2xl text-white">
                เปรียบเทียบเส้นทาง ({allRoutes.length} ตัวเลือก)
              </h3>
            </div>
            {/* Route Tabs */}
            <div className="flex flex-wrap gap-2">
              {allRoutes.map((r, idx) => (
                <button
                  key={r.route_id}
                  onClick={() => setSelectedRouteIndex(idx)}
                  className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold transition ${
                    selectedRouteIndex === idx
                      ? "bg-aqua text-white shadow-md"
                      : "bg-white/10 text-white/75 hover:bg-white/15 hover:text-white"
                  }`}
                >
                  <Navigation size={13} />
                  <span>{r.isPrimary ? "เส้นทางหลัก" : `ทางเลือก #${idx}`}</span>
                </button>
              ))}
            </div>
          </div>

          {currentRoute && (
            <div className="mt-6 grid gap-6 md:grid-cols-[1.2fr_.8fr]">
              {/* Route Summary & Steps */}
              <div className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-5 text-white">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
                  <div>
                    <span className="text-xs text-white/50">{currentRoute.label ?? "รายละเอียดเส้นทาง"}</span>
                    <div className="mt-1 flex items-center gap-2">
                      <b className="text-lg text-white">
                        {currentRoute.distance_km != null ? formatDistance(currentRoute.distance_km) : "—"}
                      </b>
                      <span className="text-white/40">·</span>
                      <span className="text-sm text-white/80">
                        {currentRoute.duration_minutes != null
                          ? formatDuration(currentRoute.duration_minutes)
                          : "—"}
                      </span>
                    </div>
                  </div>
                  {currentRoute.risk_level && (
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                        currentRoute.risk_level === "HIGH"
                          ? "bg-red-500/20 text-red-300"
                          : currentRoute.risk_level === "MEDIUM"
                            ? "bg-amber-500/20 text-amber-300"
                            : "bg-sky-500/20 text-sky-300"
                      }`}
                    >
                      {currentRoute.risk_level} RISK
                    </span>
                  )}
                </div>

                {/* Timeline Legs */}
                <div>
                  <p className="mb-3 text-xs font-bold tracking-wider text-white/60">ขั้นตอนการเดินทาง (Legs):</p>
                  {currentRoute.legs && currentRoute.legs.length > 0 ? (
                    <div className="space-y-2 border-l-2 border-aqua/40 pl-4 text-xs">
                      {currentRoute.legs.map((leg, i) => (
                        <div key={i} className="relative space-y-1 pb-2">
                          <div className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-aqua" />
                          <div className="flex flex-wrap items-center justify-between gap-2 font-bold text-white">
                            <span>
                              {leg.from ?? "จุดเริ่มต้น"} → {leg.to ?? "จุดหมาย"}
                            </span>
                            {leg.service_status && (
                              <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-[#b9e5fb]">
                                {leg.service_status}
                              </span>
                            )}
                          </div>
                          <div className="text-white/60">
                            โหมด: {leg.mode} {leg.operator ? `· ผู้ให้บริการ: ${leg.operator}` : ""}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-white/50">เดินทางรวดเดียวตามแนวถนนสายหลัก</p>
                  )}
                </div>
              </div>

              {/* Tips & Restrictions */}
              <div className="space-y-4">
                {currentRoute.tips && currentRoute.tips.length > 0 && (
                  <div className="rounded-xl border border-sky-400/20 bg-sky-900/20 p-4 text-xs text-sky-100">
                    <p className="flex items-center gap-1.5 font-bold text-[#b9e5fb]">
                      <Lightbulb size={15} /> คำแนะนำสำหรับการเดินทางนี้
                    </p>
                    <ul className="mt-2 space-y-1 text-white/80">
                      {currentRoute.tips.map((tip, idx) => (
                        <li key={idx} className="flex items-start gap-1.5">
                          <span className="text-aqua">•</span>
                          <span>{tip}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {currentRoute.restrictions && currentRoute.restrictions.length > 0 && (
                  <div className="rounded-xl border border-amber-400/20 bg-amber-900/20 p-4 text-xs text-amber-100">
                    <p className="flex items-center gap-1.5 font-bold text-amber-300">
                      <AlertTriangle size={15} /> ข้อจำกัดและข้อควรระวัง
                    </p>
                    <ul className="mt-2 space-y-1 text-white/80">
                      {currentRoute.restrictions.map((res, idx) => (
                        <li key={idx} className="flex items-start gap-1.5">
                          <span className="text-amber-400">•</span>
                          <span>{res}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Row 3: Active Hazards & System Warnings */}
      {recommendation.hazards && recommendation.hazards.length > 0 && (
        <section className="rounded-2xl border border-red-500/30 bg-red-950/25 p-5 text-white">
          <div className="flex items-center gap-2">
            <ShieldAlert className="text-red-400" size={20} />
            <h4 className="font-bold text-red-100">ประกาศเตือนภัยบนแนวเส้นทาง (Active Hazards)</h4>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {recommendation.hazards.map((h) => (
              <div key={h.hazard_id} className="rounded-xl border border-red-400/20 bg-black/20 p-3.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-red-200">{h.title}</span>
                  <span className="rounded bg-red-500/30 px-1.5 py-0.5 text-[10px] font-bold text-red-200">
                    {h.severity}
                  </span>
                </div>
                {h.area && typeof h.area === "object" && "description" in h.area && (
                  <p className="mt-1 text-white/70">{String(h.area.description)}</p>
                )}
                {h.starts_at && (
                  <p className="mt-2 text-[11px] text-white/50">
                    เริ่ม: {new Date(h.starts_at).toLocaleTimeString("th-TH")}
                    {h.ends_at ? ` · สิ้นสุด: ${new Date(h.ends_at).toLocaleTimeString("th-TH")}` : ""}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {recommendation.warnings && recommendation.warnings.length > 0 && (
        <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 p-4 text-xs text-amber-200">
          <p className="flex items-center gap-1.5 font-bold">
            <CircleAlert size={16} /> การแจ้งเตือนจากระบบ (System Warnings):
          </p>
          <ul className="mt-1.5 space-y-1">
            {recommendation.warnings.map((w, idx) => (
              <li key={idx}>• {w.message} ({w.code})</li>
            ))}
          </ul>
        </div>
      )}

      {/* Row 4: Emergency Instructions */}
      {recommendation.emergency_instructions && (
        <div className="rounded-2xl border border-red-400/30 bg-red-500/15 p-6 text-sm text-red-50">
          <p className="flex items-center gap-2 text-base font-bold text-red-200">
            <CircleAlert size={20} /> แผนปฏิบัติกรณีฉุกเฉิน (Emergency Instructions)
          </p>
          <p className="mt-3 leading-relaxed text-red-100">{recommendation.emergency_instructions.what_to_do_now}</p>

          {recommendation.emergency_instructions.safety_steps.length > 0 && (
            <div className="mt-4">
              <b className="block text-xs font-bold uppercase tracking-wider text-red-200">ข้อควรปฏิบัติเพื่อความปลอดภัย:</b>
              <ul className="mt-2 space-y-1.5 text-xs text-red-100/90">
                {recommendation.emergency_instructions.safety_steps.map((step) => (
                  <li key={step} className="flex items-start gap-1.5">
                    <span className="text-red-300">✓</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {recommendation.emergency_instructions.contacts.length > 0 && (
            <div className="mt-5 border-t border-red-400/20 pt-4">
              <b className="block text-xs font-bold text-red-200">เบอร์โทรศัพท์ฉุกเฉิน:</b>
              <div className="mt-2 flex flex-wrap gap-3">
                {recommendation.emergency_instructions.contacts.map((c) => (
                  <a
                    key={c.phone}
                    href={`tel:${c.phone}`}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-red-600/30 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-600/50"
                  >
                    <Phone size={13} /> {c.name}: {c.phone}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Row 5: Data Sources & Freshness Breakdown */}
      {recommendation.data_freshness?.items && recommendation.data_freshness.items.length > 0 && (
        <details className="group rounded-xl border border-white/10 bg-white/5 p-4 text-xs text-white">
          <summary className="flex cursor-pointer items-center justify-between font-bold text-white/80 hover:text-white">
            <span className="flex items-center gap-2">
              <Clock3 size={15} className="text-aqua" />
              รายละเอียดความสดใหม่ของข้อมูลแยกตามหมวดหมู่ (Data Freshness Details)
            </span>
            <span className="text-aqua transition group-open:rotate-180">▼</span>
          </summary>
          <div className="mt-4 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {recommendation.data_freshness.items.map((item) => (
              <div key={item.category} className="rounded-lg bg-white/5 p-3">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white">{CATEGORY_LABEL[item.category] ?? item.category}</span>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${item.is_stale ? "bg-amber-500/20 text-amber-300" : "bg-sky-500/20 text-sky-300"}`}>
                    {item.is_stale ? "ล้าสมัย" : "สดใหม่"}
                  </span>
                </div>
                <p className="mt-2 text-white/50">
                  {item.age_seconds != null ? `อัปเดต ${formatAge(item.age_seconds)}` : "พร้อมใช้งาน"}
                </p>
              </div>
            ))}
          </div>

          {/* Sources List */}
          {recommendation.sources && recommendation.sources.length > 0 && (
            <div className="mt-4 border-t border-white/10 pt-3">
              <span className="text-[11px] font-bold text-white/60">แหล่งข้อมูลอ้างอิง:</span>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {recommendation.sources.map((s) => (
                  <span key={s.source_id} className="inline-flex items-center gap-1 rounded bg-white/5 px-2.5 py-1 text-[11px] text-white/80">
                    {s.name}
                    {s.url && (
                      <a href={s.url} target="_blank" rel="noreferrer" className="text-aqua hover:underline">
                        <ExternalLink size={11} />
                      </a>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}
        </details>
      )}

      {/* Row 6: User Feedback Submission */}
      <section className="rounded-2xl border border-white/15 bg-white/5 p-6 text-white backdrop-blur">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <p className="text-xs font-bold tracking-widest text-[#b9e5fb]">FEEDBACK</p>
            <h4 className="mt-1 font-display text-xl">คำแนะนำนี้เป็นประโยชน์ต่อการเดินทางของคุณหรือไม่?</h4>
          </div>

          {feedbackSubmitted ? (
            <div className="flex items-center gap-2 rounded-xl bg-emerald-500/20 px-4 py-2.5 text-xs font-bold text-emerald-200">
              <CheckCircle2 size={16} /> ขอบคุณสำหรับความคิดเห็นของคุณ!
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => setFeedbackHelpful(true)}
                className={`flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold transition ${
                  feedbackHelpful === true
                    ? "bg-emerald-500 text-white shadow-md"
                    : "bg-white/10 text-white/70 hover:bg-white/20 hover:text-white"
                }`}
              >
                <ThumbsUp size={14} /> มีประโยชน์
              </button>
              <button
                type="button"
                onClick={() => setFeedbackHelpful(false)}
                className={`flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold transition ${
                  feedbackHelpful === false
                    ? "bg-amber-600 text-white shadow-md"
                    : "bg-white/10 text-white/70 hover:bg-white/20 hover:text-white"
                }`}
              >
                <ThumbsDown size={14} /> ไม่เป็นประโยชน์
              </button>
            </div>
          )}
        </div>

        {!feedbackSubmitted && feedbackHelpful !== null && (
          <div className="mt-4 border-t border-white/10 pt-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-white/60">ให้คะแนนความพึงพอใจ:</span>
              <div className="flex gap-1 text-amber-300">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setFeedbackRating(star)}
                    className="p-1 hover:scale-110 transition"
                  >
                    <Star
                      size={18}
                      className={star <= feedbackRating ? "fill-amber-300 text-amber-300" : "text-white/30"}
                    />
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-3 flex gap-2">
              <input
                type="text"
                value={feedbackComment}
                onChange={(e) => setFeedbackComment(e.target.value)}
                placeholder="ข้อเสนอแนะเพิ่มเติม (ไม่บังคับ)…"
                className="w-full rounded-xl border border-white/15 bg-white/10 px-3.5 py-2 text-xs text-white placeholder-white/40 outline-none focus:border-aqua"
              />
              <button
                type="button"
                onClick={handleSendFeedback}
                disabled={isSubmittingFeedback}
                className="flex shrink-0 items-center gap-1.5 rounded-xl bg-aqua px-4 py-2 text-xs font-bold text-white hover:bg-pine transition disabled:opacity-50"
              >
                {isSubmittingFeedback ? <LoaderCircle size={14} className="animate-spin" /> : <Send size={14} />}
                ส่งคำติชม
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Row 7: Disclaimer & Engine Versions */}
      <div className="flex flex-col justify-between gap-2 border-t border-white/10 pt-4 text-[11px] text-white/45 sm:flex-row">
        <span>
          {recommendation.disclaimer ??
            "คำแนะนำนี้จัดทำขึ้นเพื่อช่วยในการตัดสินใจ โปรดตรวจสอบความปลอดภัยและประกาศจากทางการก่อนเดินทาง"}
        </span>
        {recommendation.versions && (
          <span className="shrink-0 font-mono">
            API: {recommendation.versions.api} · Risk Model: {recommendation.versions.risk_model ?? "v1"}
          </span>
        )}
      </div>
    </div>
  );
}

function EnvironmentSignalsSection({
  factors,
  hazards,
  usingMock,
  dataFreshness,
  sourcesCount,
}: {
  factors: RiskFactor[];
  hazards: Hazard[];
  usingMock: boolean;
  dataFreshness?: DataFreshness | null;
  sourcesCount: number;
}) {
  const [showTrafficDetails, setShowTrafficDetails] = useState(false);

  // 1. Group factors by category
  const transportFactors = factors.filter((f) => f.type.toUpperCase() === "TRANSPORT");
  const weatherFactors = factors.filter((f) => f.type.toUpperCase() === "WEATHER");
  const otherFactors = factors.filter(
    (f) => f.type.toUpperCase() !== "WEATHER" && f.type.toUpperCase() !== "TRANSPORT"
  );

  // 2. Traffic Analysis & Smart Aggregation
  const hasTrafficHigh = transportFactors.some((f) => f.level === "HIGH");
  const hasTrafficMed = transportFactors.some((f) => f.level === "MEDIUM");
  const trafficLevel: RiskLevel = hasTrafficHigh ? "HIGH" : hasTrafficMed ? "MEDIUM" : "LOW";

  const trafficRecordIds: string[] = [];
  for (const f of transportFactors) {
    const match = f.description.match(/(?:longdo:|#)?(\d{5,})/i);
    if (match) {
      trafficRecordIds.push(match[1]);
    }
  }

  const isRawTrafficLog = transportFactors.some((f) =>
    /record/i.test(f.description) || /disruption/i.test(f.description) || /longdo/i.test(f.description)
  );

  let trafficTitle = "สภาพการจราจรและการสัญจร";
  let trafficDesc = "";
  let trafficTip = "";

  if (transportFactors.length > 0) {
    if (isRawTrafficLog) {
      const count = transportFactors.length;
      if (trafficLevel === "HIGH") {
        trafficTitle = `ตรวจพบจุดติดขัดวิกฤตหรือกีดขวางการจราจร (${count} จุด)`;
        trafficDesc = `มีรายงานเส้นทางถูกปิดกั้น เกิดอุบัติเหตุกีดขวาง หรือการจราจรติดขัดรุนแรง ${count} จุดตามแนวเส้นทาง อาจส่งผลกระทบต่อเวลาการเดินทางอย่างมาก`;
        trafficTip = "แนะนำให้พิจารณาใช้เส้นทางสำรองที่ระบบเสนอ หรือเลี่ยงการออกเดินทางในขณะนี้";
      } else if (trafficLevel === "MEDIUM") {
        trafficTitle = `ตรวจพบการจราจรติดขัดสะสม (${count} จุด)`;
        trafficDesc = `พบจุดชะลอตัวหนาแน่นและการจราจรสะสม ${count} ช่วงตามแนวเส้นทาง อาจทำให้ระยะเวลาเดินทางเพิ่มขึ้นกว่าปกติ`;
        trafficTip = "ควรตรวจสอบเส้นทางสำรอง หรือเผื่อเวลาเดินทางเพิ่มอย่างน้อย 25–40 นาที";
      } else {
        trafficTitle = `รายงานการจราจรชะลอตัวตามแนวเส้นทาง (${count} จุด)`;
        trafficDesc = `ตรวจพบจุดชะลอตัวหรือรถเคลื่อนตัวช้า ${count} จุดตามแนวเส้นทางหลัก ยังสามารถสัญจรผ่านได้ตามปกติ ไม่พบรายงานการปิดเส้นทางหรืออุบัติเหตุกีดขวางรุนแรง`;
        trafficTip = "แนะนำเผื่อเวลาเดินทางเพิ่มประมาณ 10–15 นาที โดยเฉพาะหากสัญจรในช่วงเวลาเร่งด่วน";
      }
    } else {
      trafficTitle = "รายงานสภาพการเดินทางและขนส่ง";
      trafficDesc = transportFactors.map((f) => f.description).join(" ");
      if (trafficLevel !== "LOW") {
        trafficTip = "ควรติดตามสภาพการจราจรอย่างต่อเนื่องตลอดการเดินทาง";
      }
    }
  }

  // 3. Weather Analysis
  const weatherCards = weatherFactors.map((f, idx) => {
    const desc = f.description;
    let title = "รายงานสภาพอากาศตามแนวเส้นทาง";
    let detail = desc;
    let tip = "";
    let IconComponent = CloudRain;

    if (/rain_probability|rain|ฝน/i.test(desc)) {
      title = "มีโอกาสเกิดฝนตกตามแนวเส้นทาง";
      detail = "ระบบตรวจพบความชื้นและโอกาสเกิดฝนตกในพื้นที่ อาจทำให้ผิวถนนเปียกลื่นและทัศนวิสัยลดลง";
      tip = "เปิดที่ปัดน้ำฝน ลดความเร็วลง 10-20 กม./ชม. และเว้นระยะห่างจากคันหน้าเพื่อความปลอดภัย";
      IconComponent = CloudRain;
    } else if (/visibility|ทัศนวิสัย/i.test(desc)) {
      title = "ทัศนวิสัยการมองเห็นลดลง";
      detail = "มีหมอก ควัน หรือฝนบดบังทัศนวิสัยในการขับขี่ตามแนวเส้นทาง";
      tip = "เปิดไฟหน้ารถ หลีกเลี่ยงการเปิดไฟฉุกเฉินขณะรถกำลังวิ่ง และเพิ่มความระมัดระวัง";
      IconComponent = Waves;
    } else if (/wind|ลม/i.test(desc)) {
      title = "มีลมกระโชกแรงในบางช่วง";
      detail = "ตรวจพบกระแสลมแรงในบางจุดของเส้นทาง อาจกระทบต่อการทรงตัวของยานพาหนะ";
      tip = "ควบคุมพวงมาลัยด้วยความมั่นคง และชะลอความเร็วเมื่อขับขี่บนสะพานหรือเส้นทางโล่ง";
      IconComponent = Waves;
    } else if (desc.startsWith("Weather record")) {
      title = "รายงานสภาพอากาศตามแนวเส้นทาง";
      detail = `ตรวจพบปัจจัยด้านสภาพอากาศระดับ ${f.level} ที่อาจส่งผลต่อการเดินทาง`;
      tip = "ขับขี่ด้วยความระมัดระวังและตรวจสอบสภาพอากาศเป็นระยะ";
      IconComponent = CloudRain;
    }

    return {
      key: `weather-${idx}`,
      title,
      detail,
      tip,
      level: f.level,
      IconComponent,
    };
  });

  // 4. Quick-Glance 3-Pillar Status Bar
  let trafficPillarText = "คล่องตัวปกติ";
  let trafficPillarBg = "bg-emerald-100 text-emerald-700";
  if (transportFactors.length > 0) {
    if (trafficLevel === "HIGH") {
      trafficPillarText = `ติดขัดหนัก (${transportFactors.length} จุด)`;
      trafficPillarBg = "bg-rose-100 text-rose-700";
    } else if (trafficLevel === "MEDIUM") {
      trafficPillarText = `ติดขัดสะสม (${transportFactors.length} จุด)`;
      trafficPillarBg = "bg-amber-100 text-amber-800";
    } else {
      trafficPillarText = `ชะลอตัว (${transportFactors.length} จุด)`;
      trafficPillarBg = "bg-sky-100 text-sky-800";
    }
  }

  let weatherPillarText = "ปกติ / ปลอดโปร่ง";
  let weatherPillarBg = "bg-emerald-100 text-emerald-700";
  if (weatherFactors.length > 0) {
    const hasHighWeather = weatherFactors.some((f) => f.level === "HIGH");
    if (hasHighWeather) {
      weatherPillarText = "สภาพอากาศรุนแรง";
      weatherPillarBg = "bg-rose-100 text-rose-700";
    } else if (weatherFactors.some((f) => /rain|ฝน/i.test(f.description))) {
      weatherPillarText = "มีฝนตกบางช่วง";
      weatherPillarBg = "bg-sky-100 text-sky-800";
    } else if (weatherFactors.some((f) => /visibility|ทัศนวิสัย/i.test(f.description))) {
      weatherPillarText = "ทัศนวิสัยลดลง";
      weatherPillarBg = "bg-amber-100 text-amber-800";
    } else {
      weatherPillarText = "สภาพอากาศแปรปรวน";
      weatherPillarBg = "bg-amber-100 text-amber-800";
    }
  }

  const hazardList = hazards ?? [];
  let hazardPillarText = "ปลอดภัย ไม่มีเตือนภัย";
  let hazardPillarBg = "bg-emerald-100 text-emerald-700";
  if (hazardList.length > 0) {
    const hasCritical = hazardList.some((h) => h.severity === "HIGH");
    hazardPillarText = hasCritical ? `เตือนภัยวิกฤต (${hazardList.length})` : `มีประกาศเตือน (${hazardList.length})`;
    hazardPillarBg = hasCritical ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-800";
  }

  const isAllClear =
    transportFactors.length === 0 &&
    weatherFactors.length === 0 &&
    hazardList.length === 0 &&
    otherFactors.length === 0;

  const getLevelBadge = (level: RiskLevel) => {
    switch (level) {
      case "HIGH":
        return { text: "วิกฤต (HIGH)", badge: "bg-rose-50 text-rose-700 border border-rose-200" };
      case "MEDIUM":
        return { text: "ควรระวัง (MEDIUM)", badge: "bg-amber-50 text-amber-800 border border-amber-200" };
      default:
        return { text: "ผลกระทบต่ำ (LOW)", badge: "bg-sky-50 text-sky-700 border border-sky-200" };
    }
  };

  return (
    <article className="flex flex-col justify-between rounded-2xl border border-sky-100 bg-[#eef7fc] p-6 text-slate-800 shadow-sm sm:p-8">
      <div>
        {/* Header with Thai labels & Live indicator */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold tracking-[.18em] text-[#0284c7]">
              สัญญาณและสภาพแวดล้อมสด (ENVIRONMENT SIGNALS)
            </p>
            <h3 className="mt-1 font-display text-2xl text-slate-900">
              สถานการณ์สดตลอดเส้นทาง
            </h3>
          </div>
          <span
            className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
              usingMock
                ? "border border-amber-200 bg-amber-50 text-amber-800"
                : "border border-emerald-200 bg-emerald-50 text-emerald-800"
            }`}
          >
            {!usingMock && <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />}
            {usingMock ? "โหมดตัวอย่าง (DEMO)" : "ตรวจสอบสดเรียลไทม์ (LIVE)"}
          </span>
        </div>

        {/* 3-Pillar Quick Summary Bar */}
        <div className="mt-5 grid grid-cols-1 gap-2.5 rounded-xl border border-slate-200/80 bg-white/90 p-3 shadow-xs sm:grid-cols-3">
          <div className="flex items-center gap-2.5 p-1">
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${trafficPillarBg}`}>
              <Car size={18} />
            </div>
            <div className="min-w-0">
              <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                การจราจร
              </span>
              <p className="truncate text-xs font-bold text-slate-800" title={trafficPillarText}>
                {trafficPillarText}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 border-t border-slate-200/60 p-1 pt-2 sm:border-l sm:border-t-0 sm:pl-2.5 sm:pt-1">
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${weatherPillarBg}`}>
              <CloudRain size={18} />
            </div>
            <div className="min-w-0">
              <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                สภาพอากาศ
              </span>
              <p className="truncate text-xs font-bold text-slate-800" title={weatherPillarText}>
                {weatherPillarText}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 border-t border-slate-200/60 p-1 pt-2 sm:border-l sm:border-t-0 sm:pl-2.5 sm:pt-1">
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${hazardPillarBg}`}>
              <ShieldCheck size={18} />
            </div>
            <div className="min-w-0">
              <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                ภัยพิบัติ / ฉุกเฉิน
              </span>
              <p className="truncate text-xs font-bold text-slate-800" title={hazardPillarText}>
                {hazardPillarText}
              </p>
            </div>
          </div>
        </div>

        {/* Detailed Signal Cards */}
        <div className="mt-5 space-y-3">
          {/* All clear reassuring state */}
          {isAllClear && (
            <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 shadow-xs">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700">
                <CheckCircle2 size={18} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-emerald-900">สถานะเส้นทาง</span>
                  <span className="rounded-full border border-emerald-200 bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                    ปลอดภัย (CLEAR)
                  </span>
                </div>
                <h4 className="mt-1 text-sm font-bold text-emerald-950">
                  สภาพแวดล้อมตลอดเส้นทางเป็นปกติ
                </h4>
                <p className="mt-1 text-xs leading-relaxed text-emerald-800/90">
                  ระบบตรวจสอบไม่พบรายงานอุบัติเหตุ จุดติดขัดสะสม สภาพอากาศรุนแรง หรือประกาศเตือนภัยบนแนวเส้นทางนี้ สามารถเดินทางได้ตามปกติ
                </p>
              </div>
            </div>
          )}

          {/* Traffic Card */}
          {transportFactors.length > 0 && (
            <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs transition hover:shadow-sm">
              <div className="flex items-start gap-3">
                <div
                  className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                    trafficLevel === "HIGH"
                      ? "bg-rose-100 text-rose-700"
                      : trafficLevel === "MEDIUM"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-sky-100 text-sky-800"
                  }`}
                >
                  <Car size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-bold text-slate-900">การจราจรและสภาพถนน</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${getLevelBadge(trafficLevel).badge}`}>
                      {getLevelBadge(trafficLevel).text}
                    </span>
                  </div>
                  <h4 className="mt-1 text-sm font-bold text-slate-800">{trafficTitle}</h4>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{trafficDesc}</p>

                  {/* Travel Advice Tip */}
                  {trafficTip && (
                    <div className="mt-3 flex items-start gap-2 rounded-lg border border-sky-100 bg-sky-50 p-2.5 text-xs text-sky-900">
                      <Lightbulb size={15} className="mt-0.5 shrink-0 text-sky-600" />
                      <span className="font-medium">{trafficTip}</span>
                    </div>
                  )}

                  {/* Collapsible reference points */}
                  {trafficRecordIds.length > 0 && (
                    <div className="mt-3 border-t border-slate-100 pt-2.5">
                      <button
                        type="button"
                        onClick={() => setShowTrafficDetails(!showTrafficDetails)}
                        className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 hover:text-slate-800 transition"
                      >
                        <span>
                          {showTrafficDetails
                            ? "ซ่อนรายละเอียดจุดตรวจสอบ"
                            : `ดูจุดตรวจสอบอ้างอิง Longdo Traffic ทั้งหมด (${trafficRecordIds.length} จุด)`}
                        </span>
                        {showTrafficDetails ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                      </button>

                      {showTrafficDetails && (
                        <div className="mt-2 max-h-44 space-y-1.5 overflow-y-auto rounded-lg border border-slate-200/60 bg-slate-50 p-2.5">
                          <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                            ข้อมูลตรวจจับสดจากเครือข่าย iTIC / Longdo Traffic:
                          </p>
                          {trafficRecordIds.map((id, idx) => (
                            <div key={`${id}-${idx}`} className="flex items-center justify-between py-0.5 text-xs text-slate-600">
                              <span className="flex items-center gap-1.5 font-mono text-[11px]">
                                <MapPin size={12} className="text-slate-400" />
                                จุดที่ {idx + 1}: รหัส {id}
                              </span>
                              <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] text-slate-500">
                                รายงาน: ชะลอตัว / ล่าช้า
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Weather Cards */}
          {weatherCards.map((item) => {
            const IconCmp = item.IconComponent;
            const badge = getLevelBadge(item.level);
            return (
              <div
                key={item.key}
                className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs transition hover:shadow-sm"
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                      item.level === "HIGH"
                        ? "bg-rose-100 text-rose-700"
                        : item.level === "MEDIUM"
                          ? "bg-amber-100 text-amber-800"
                          : "bg-sky-100 text-sky-800"
                    }`}
                  >
                    <IconCmp size={18} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-bold text-slate-900">สภาพอากาศและทัศนวิสัย</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${badge.badge}`}>
                        {badge.text}
                      </span>
                    </div>
                    <h4 className="mt-1 text-sm font-bold text-slate-800">{item.title}</h4>
                    <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{item.detail}</p>
                    {item.tip && (
                      <div className="mt-3 flex items-start gap-2 rounded-lg border border-sky-100 bg-sky-50 p-2.5 text-xs text-sky-900">
                        <Lightbulb size={15} className="mt-0.5 shrink-0 text-sky-600" />
                        <span className="font-medium">{item.tip}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {/* Hazards & Alerts from recommendation.hazards */}
          {hazardList.map((hazard) => (
            <div
              key={hazard.hazard_id}
              className="rounded-xl border border-red-200 bg-red-50/60 p-4 shadow-xs"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-100 text-red-700">
                  <AlertTriangle size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold text-red-900">ประกาศเตือนภัยพิเศษ</span>
                    <span className="rounded-full border border-red-200 bg-red-100 px-2 py-0.5 text-[10px] font-bold text-red-800">
                      {hazard.severity === "HIGH" ? "วิกฤต (HIGH)" : hazard.severity === "MEDIUM" ? "เตือนภัย (MEDIUM)" : "เฝ้าระวัง (LOW)"}
                    </span>
                  </div>
                  <h4 className="mt-1 text-sm font-bold text-red-950">{hazard.title}</h4>
                  {hazard.starts_at && (
                    <p className="mt-1 text-xs text-red-700">
                      มีผลตั้งแต่: {new Date(hazard.starts_at).toLocaleDateString("th-TH")}{" "}
                      {new Date(hazard.starts_at).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" })} น.
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Other Factors if any */}
          {otherFactors.map((f, idx) => {
            const badge = getLevelBadge(f.level);
            return (
              <div
                key={`other-${idx}`}
                className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs transition hover:shadow-sm"
              >
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
                    <Route size={18} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold text-slate-900">
                        {CATEGORY_LABEL[f.type as DataCategory] ?? f.type}
                      </span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${badge.badge}`}>
                        {badge.text}
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-slate-600">{f.description}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Freshness & Attribution summary */}
      <div className="mt-6 border-t border-slate-200/80 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
          <span className="flex items-center gap-1.5">
            <Clock3 size={15} className="text-aqua" />
            {usingMock ? (
              <span className="font-medium text-amber-700">ข้อมูลจำลองเพื่อการสาธิต (ไม่ใช่ข้อมูลสด)</span>
            ) : dataFreshness?.overall_is_stale ? (
              <b className="text-amber-700">ข้อมูลบางแหล่งอาจมีความล่าช้า</b>
            ) : dataFreshness ? (
              <span className="text-slate-700">ตรวจสอบและอัปเดตข้อมูลสดตามเวลาจริง</span>
            ) : (
              <span className="text-slate-700">เชื่อมต่อบริการข้อมูลสด</span>
            )}
          </span>
          <span className="text-[11px] text-slate-500">
            แหล่งอ้างอิง: Longdo Traffic, TMD, GDACS ({sourcesCount} แหล่งข้อมูล)
          </span>
        </div>
      </div>
    </article>
  );
}

function IdleExample({ busy, message }: { busy: boolean; message: string | null }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1.05fr_.95fr] text-left">
      <article className="rounded-2xl bg-[#102e4e] p-6 sm:p-8">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-bold tracking-[.17em] text-white/55">
              ASSESSMENT · {busy ? "กำลังประมวลผล" : "รอผลประเมิน"}
            </p>
            <div className="mt-6 flex items-center gap-3 text-[#b9e5fb]">
              {busy ? <LoaderCircle className="animate-spin" size={28} /> : <Info size={28} />}
              <span className="font-bold">{busy ? (message ?? "กำลังตรวจสอบ…").toUpperCase() : "ยังไม่ทราบระดับความเสี่ยง"}</span>
            </div>
            <h3 className="mt-3 font-display text-4xl sm:text-5xl text-white">
              {busy ? "กำลังประเมินเส้นทางของคุณ…" : "เริ่มประเมินเส้นทางของคุณ"}
            </h3>
          </div>
          <span className="rounded-full bg-white/10 p-3 text-white">
            {busy ? <LoaderCircle className="animate-spin" size={20} /> : <Info size={20} />}
          </span>
        </div>
        <p className="mt-7 max-w-md text-sm leading-7 text-white/70">
          {busy
            ? "โปรดรอสักครู่ ระบบกำลังตรวจสอบสภาพอากาศ การเดินทาง และประกาศภัยพิบัติที่เกี่ยวข้องกับเส้นทางของคุณ"
            : "กรอกแบบฟอร์มด้านบนแล้วกดส่ง เพื่อดูผลประเมินความเสี่ยงจริงของเส้นทางคุณตรงนี้"}
        </p>
        <div className="mt-8 grid grid-cols-2 border-t border-white/15 pt-5 text-sm text-white">
          <div>
            <span className="text-white/50">Risk score</span>
            <b className="mt-1 block text-xl">{busy ? "…" : "—"}</b>
          </div>
          <div>
            <span className="text-white/50">Confidence</span>
            <b className="mt-1 block text-xl">{busy ? "…" : "—"}</b>
          </div>
        </div>
      </article>

      <article className="rounded-2xl bg-[#eef7fc] p-6 text-ink sm:p-8">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-2xl">ข้อมูลสภาพแวดล้อม</h3>
          <span className="text-xs font-bold text-slate-500">รอการประเมิน</span>
        </div>
        <div className="mt-5 space-y-3">
          <div data-card className="flex gap-3 rounded-xl bg-white p-3 shadow-sm">
            <span className="text-aqua"><Waves size={17} /></span>
            <span>
              <b className="block text-sm">สภาพอากาศ</b>
              <small className="text-xs text-slate-500">จะแสดงเมื่อมีข้อมูลที่ตรวจสอบได้</small>
            </span>
          </div>
          <div data-card className="flex gap-3 rounded-xl bg-white p-3 shadow-sm">
            <span className="text-aqua"><Route size={17} /></span>
            <span>
              <b className="block text-sm">สภาพการเดินทาง</b>
              <small className="text-xs text-slate-500">จะแสดงเมื่อมีข้อมูลที่ตรวจสอบได้</small>
            </span>
          </div>
          <div data-card className="flex gap-3 rounded-xl bg-white p-3 shadow-sm">
            <span className="text-aqua"><Clock3 size={17} /></span>
            <span>
              <b className="block text-sm">เวลาข้อมูลและแหล่งอ้างอิง</b>
              <small className="text-xs text-slate-500">จะแสดงหลังส่งคำขอประเมิน</small>
            </span>
          </div>
        </div>
      </article>
    </div>
  );
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} วินาทีที่แล้ว`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} นาทีที่แล้ว`;
  return `${Math.round(minutes / 60)} ชั่วโมงที่แล้ว`;
}

function formatDuration(minutes: number): string {
  if (isNaN(minutes) || minutes <= 0) return "—";
  const roundedMinutes = Math.round(minutes);
  if (roundedMinutes < 60) return `${roundedMinutes} นาที`;
  const hrs = Math.floor(roundedMinutes / 60);
  const remMin = roundedMinutes % 60;
  return remMin > 0 ? `${hrs} ชม. ${remMin} นาที` : `${hrs} ชั่วโมง`;
}

function formatDistance(km: number): string {
  if (isNaN(km) || km < 0) return "—";
  const formatted = Math.round(km * 10) / 10;
  return `${formatted} กม.`;
}
