"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bot,
  Car,
  Check,
  ChevronRight,
  CloudRain,
  Clock,
  Navigation,
  Send,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { type TripFormInput, useTrip } from "./trip-context";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  proposal?: {
    label: string;
    changes: {
      time?: string;
      date?: string;
      origin?: string;
      destination?: string;
      mode?: "CAR" | "BUS" | "TRAIN" | "FLIGHT" | "FERRY" | "WALK" | "BICYCLE";
    };
  } | null;
  timestamp: string;
}

const QUICK_PROMPTS = [
  { label: "มีฝนตกช่วงไหนบ้าง?", icon: CloudRain },
  { label: "มีรถติดหรือปิดถนนไหม?", icon: Car },
  { label: "เส้นทางนี้ปลอดภัยไหม?", icon: ShieldAlert },
  { label: "เลื่อนเวลาออกเดินทางให้หน่อย", icon: Clock },
];

export function TravelAssistantDrawer() {
  const { recommendation, lastInput, originPoint, destinationPoint, applyAssistantChanges, status, usingMock } = useTrip();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [appliedProposalId, setAppliedProposalId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Initialize with greeting
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([
        {
          id: "welcome-1",
          role: "assistant",
          content:
            "สวัสดีครับ! ผมช่วยอธิบายผลประเมินและปรับแผนเดินทางได้ หากข้อมูลสดยังไม่พร้อม ผมจะแจ้งให้ทราบตามตรงครับ",
          timestamp: new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    }
  }, [messages.length]);

  // Auto scroll to bottom
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen]);

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim();
    if (!text || isLoading) return;

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputMessage("");
    setIsLoading(true);

    // Build context summary strictly based on verified evidence and service status
    let weatherSummary: string | undefined = undefined;
    const weatherStatus = recommendation?.service_status?.weather;

    if (weatherStatus === "unavailable") {
      weatherSummary = "ระบบไม่สามารถดึงข้อมูลสภาพอากาศได้เนื่องจากบริการสภาพอากาศภายนอกไม่พร้อมใช้งาน (Service Unavailable)";
    } else if (weatherStatus === "degraded") {
      weatherSummary = "ข้อมูลสภาพอากาศอาจไม่สมบูรณ์เนื่องจากบริการสภาพอากาศทำงานได้จำกัด (Degraded)";
    } else if (weatherStatus === "ok") {
      const weatherFactors = (recommendation?.risk?.factors ?? []).filter(
        (f) => f.type.toUpperCase() === "WEATHER"
      );
      if (weatherFactors.length > 0) {
        weatherSummary = weatherFactors.map((f) => f.description).join("; ");
      } else {
        weatherSummary = "บริการสภาพอากาศ (Open-Meteo) ตรวจสอบแล้ว ไม่พบปัจจัยเสี่ยงหรือสภาวะอากาศแปรปรวนบนเส้นทางนี้";
      }
    } else if (recommendation) {
      const weatherFactors = (recommendation?.risk?.factors ?? []).filter(
        (f) => f.type.toUpperCase() === "WEATHER"
      );
      if (weatherFactors.length > 0) {
        weatherSummary = weatherFactors.map((f) => f.description).join("; ");
      } else {
        weatherSummary = "ไม่พบรายงานปัจจัยเสี่ยงด้านสภาพอากาศในผลประเมินปัจจุบัน";
      }
    }

    let transportHazard: string | undefined = undefined;
    const transportStatus = recommendation?.service_status?.transport;
    if (transportStatus === "unavailable") {
      transportHazard = "ระบบไม่สามารถดึงข้อมูลจราจรสดได้เนื่องจากบริการข้อมูลจราจรไม่พร้อมใช้งาน (Service Unavailable)";
    } else if (recommendation?.hazards && recommendation.hazards.length > 0) {
      transportHazard = recommendation.hazards.map((h) => h.title).join("; ");
    } else if (transportStatus === "ok") {
      transportHazard = "ตรวจสอบข้อมูลจราจรแล้ว ไม่พบรายงานอุบัติเหตุร้ายแรงหรือการปิดถนนบนเส้นทางนี้";
    }

    const tripContext = {
      origin: lastInput?.origin || originPoint?.name || undefined,
      destination: lastInput?.destination || destinationPoint?.name || undefined,
      date: lastInput?.date,
      time: lastInput?.time,
      mode: lastInput?.mode,
      isDemo: usingMock,
      recommendation: recommendation
        ? {
            actionCode: recommendation.recommendation?.type ?? undefined,
            riskLevel: recommendation.risk?.level ?? undefined,
            explanation: {
              summary: recommendation.recommendation?.summary ?? undefined,
              reasons: recommendation.recommendation?.reasons,
              instructions: recommendation.emergency_instructions?.safety_steps,
            },
            weather: weatherSummary ? { summary: weatherSummary } : undefined,
            transport: transportHazard ? { hazard: transportHazard } : undefined,
          }
        : undefined,
    };

    try {
      const res = await fetch("/api/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [...messages, userMsg].map((m) => ({ role: m.role, content: m.content })),
          tripContext,
        }),
      });

      if (!res.ok) {
        throw new Error("Chat request failed");
      }

      const data = await res.json();
      const assistantMsg: Message = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: data.reply || "ได้รับข้อมูลแล้วครับ",
        proposal: data.proposal || null,
        timestamp: new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: "ขออภัยครับ ขณะนี้มีข้อขัดข้องในการเชื่อมต่อระบบตอบรับ กรุณาลองใหม่อีกครั้งครับ",
          timestamp: new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleApplyProposal = async (
    msgId: string,
    changes: Partial<TripFormInput> | undefined,
  ) => {
    if (!changes) return;
    setAppliedProposalId(msgId);
    await applyAssistantChanges(changes);
  };

  const handleClearChat = () => {
    setMessages([
      {
        id: `welcome-${Date.now()}`,
        role: "assistant",
        content: "เริ่มบทสนทนาใหม่แล้วครับ สามารถพิมพ์คำถามหรือบอกให้ผมช่วยวางแผนทริปได้เลยครับ",
        timestamp: new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
  };

  return (
    <>
      {/* Floating Action Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-[1200] flex items-center gap-2.5 rounded-full bg-gradient-to-r from-sky-600 via-indigo-600 to-cyan-500 px-4 py-3.5 text-white shadow-2xl transition-all duration-300 hover:scale-105 hover:shadow-indigo-500/30 active:scale-95 group"
          title="เปิดหน้าต่างแชตผู้ช่วยเดินทางอัจฉริยะ"
        >
          <div className="relative">
            <Bot className="h-6 w-6 transition-transform group-hover:rotate-12" />
            <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-400"></span>
            </span>
          </div>
          <span className="font-medium text-sm pr-1 hidden sm:inline-block tracking-wide">
            ผู้ช่วยเดินทาง AI
          </span>
        </button>
      )}

      {/* Floating Chat Drawer Window */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-[1200] flex h-[82vh] max-h-[640px] w-[92vw] sm:w-[420px] flex-col overflow-hidden rounded-2xl border border-slate-700/60 bg-slate-900/95 backdrop-blur-2xl shadow-2xl text-slate-100 transition-all duration-300 animate-in fade-in slide-in-from-bottom-6">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/60 px-4 py-3">
            <div className="flex items-center gap-2.5">
              <div className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 text-white shadow-md">
                <Bot className="h-5 w-5" />
                <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-slate-900 bg-emerald-400" />
              </div>
              <div>
                <div className="flex items-center gap-1.5 font-semibold text-sm text-slate-100">
                  <span>ผู้ช่วยเดินทางอัจฉริยะ</span>
                  <Sparkles className="h-3.5 w-3.5 text-amber-400 animate-pulse" />
                </div>
                <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  <span>อธิบายตามข้อมูลที่มี</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleClearChat}
                className="flex h-11 w-11 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200"
                title="ล้างบทสนทนา"
                aria-label="ล้างบทสนทนา"
              >
                <Trash2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="flex h-11 w-11 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200"
                title="ปิดหน้าต่างแชต"
                aria-label="ปิดหน้าต่างแชต"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Current Trip Context Banner */}
          {(lastInput || recommendation) && (
            <div className="border-b border-slate-800/80 bg-slate-950/40 px-3.5 py-2 text-[11px] text-slate-300 flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 truncate">
                <Navigation className="h-3 w-3 text-sky-400 shrink-0" />
                <span className="truncate">
                  {lastInput?.origin || originPoint?.name || "ต้นทาง"} ➔{" "}
                  {lastInput?.destination || destinationPoint?.name || "ปลายทาง"}
                </span>
              </div>
              {recommendation && (
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 font-medium ${
                    recommendation.risk?.level === "HIGH"
                      ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                      : recommendation.risk?.level === "MEDIUM"
                      ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                      : recommendation.risk?.level === "LOW"
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                      : "bg-slate-500/20 text-slate-300 border border-slate-500/30"
                  }`}
                >
                  {recommendation.recommendation?.type ?? "กำลังตรวจสอบ"}
                </span>
              )}
            </div>
          )}

          {/* Messages Container */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3.5 scrollbar-thin scrollbar-thumb-slate-700">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-gradient-to-r from-sky-600 to-indigo-600 text-white rounded-br-none shadow-md"
                      : "bg-slate-800/90 text-slate-100 rounded-bl-none border border-slate-700/60 shadow-md"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>

                  {/* Action Proposal Card */}
                  {msg.proposal && (
                    <div className="mt-3 overflow-hidden rounded-xl border border-indigo-500/40 bg-indigo-950/40 p-3 text-xs text-indigo-200">
                      <div className="flex items-center gap-1.5 font-medium text-indigo-300 mb-1.5">
                        <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                        <span>ข้อเสนอแนะปรับเปลี่ยนทริป</span>
                      </div>
                      <p className="text-slate-200 mb-2.5 font-normal">{msg.proposal.label}</p>

                      <button
                        onClick={() => handleApplyProposal(msg.id, msg.proposal?.changes)}
                        disabled={appliedProposalId === msg.id || status === "submitting"}
                        className={`flex w-full items-center justify-center gap-1.5 rounded-lg py-2 px-3 text-xs font-medium transition-all ${
                          appliedProposalId === msg.id
                            ? "bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 cursor-default"
                            : "bg-indigo-600 hover:bg-indigo-500 text-white shadow hover:shadow-indigo-500/25 active:scale-95"
                        }`}
                      >
                        {appliedProposalId === msg.id ? (
                          <>
                            <Check className="h-3.5 w-3.5 text-emerald-400" />
                            <span>อัปเดตแผนการเดินทางแล้ว</span>
                          </>
                        ) : (
                          <>
                            <span>นำไปใช้กับแผนการเดินทาง (Apply)</span>
                            <ChevronRight className="h-3.5 w-3.5" />
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
                <span className="mt-1 px-1 text-[10px] text-slate-500">{msg.timestamp}</span>
              </div>
            ))}

            {isLoading && (
              <div className="flex items-center gap-2 rounded-2xl rounded-bl-none border border-slate-700/60 bg-slate-800/90 px-4 py-3 text-sm text-slate-400 max-w-[75%]">
                <div className="flex space-x-1">
                  <div className="h-2 w-2 rounded-full bg-sky-400 animate-bounce [animation-delay:-0.3s]"></div>
                  <div className="h-2 w-2 rounded-full bg-sky-400 animate-bounce [animation-delay:-0.15s]"></div>
                  <div className="h-2 w-2 rounded-full bg-sky-400 animate-bounce"></div>
                </div>
                <span className="text-xs text-slate-400">กำลังค้นหาและวิเคราะห์ข้อมูล...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Prompts Carousel */}
          <div className="border-t border-slate-800/80 bg-slate-950/40 px-3 py-2">
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none text-[11px]">
              {QUICK_PROMPTS.map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => handleSendMessage(p.label)}
                  disabled={isLoading}
                  className="flex min-h-11 shrink-0 items-center gap-1.5 rounded-full border border-slate-700/70 bg-slate-800/60 px-3 text-slate-300 transition-colors hover:border-sky-500 hover:bg-slate-800 hover:text-white"
                >
                  <p.icon aria-hidden className="h-4 w-4" />
                  <span>{p.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Input Footer */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="border-t border-slate-800 bg-slate-950/90 p-3"
          >
            <div className="flex items-center gap-2 rounded-xl border border-slate-700/80 bg-slate-900 px-3 py-1.5 focus-within:border-sky-500 transition-colors">
              <label htmlFor="travel-assistant-message" className="sr-only">
                ข้อความถึงผู้ช่วยเดินทาง
              </label>
              <input
                id="travel-assistant-message"
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                placeholder="พิมพ์ถามสภาพอากาศ จราจร หรือสั่งปรับทริป..."
                disabled={isLoading}
                className="flex-1 bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
              />
              <button
                type="submit"
                disabled={!inputMessage.trim() || isLoading}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-sky-600 text-white transition-all hover:bg-sky-500 disabled:opacity-40 disabled:hover:bg-sky-600"
                aria-label="ส่งข้อความ"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
