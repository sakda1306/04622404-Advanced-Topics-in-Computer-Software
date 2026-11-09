"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Loader2, MessageCircle, SendHorizontal } from "lucide-react";
import { data } from "@/lib/data";
import { refreshQuota, useSession } from "@/lib/session";
import { TextWithCitations } from "@/components/app/citation";
import { EditProposalCard } from "@/components/chat/edit-proposal-card";
import { Button, ErrorState, LoadingBlock } from "@/components/intake/ui";

// Chat with AI (DesignSystem.md section 3: chat bubble, chat input; FR-8 – FR-10).
// Used as the แชท tab on /start and as the side panel / bottom sheet on the
// profile page. Every message counts toward the quota, so the input is disabled
// with the reset time when the quota is used up.

const MAX = 1000;
const SLOW_MS = 5000;
const timeTh = (iso) => new Date(iso).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" });

function Bubble({ message, onApplied }) {
  const mine = message.role === "user";
  const ref = useRef(null);
  const [long, setLong] = useState(false);
  const [expanded, setExpanded] = useState(false);

  // Long answers collapse after 12 lines.
  useLayoutEffect(() => {
    const el = ref.current;
    if (el && !mine) setLong(el.scrollHeight > el.clientHeight + 2);
  }, [message.text, mine]);

  return (
    <li className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-4 py-3 text-body ${
          mine ? "border border-border bg-bg text-text" : "bg-primary-subtle text-text"
        }`}
      >
        <span className="sr-only">{mine ? "คุณ: " : "AI: "}</span>
        <div ref={ref} className={`whitespace-pre-line break-words ${!mine && !expanded ? "line-clamp-[12]" : ""}`}>
          {mine ? message.text : <TextWithCitations text={message.text} sources={message.sources} />}
        </div>
        {long && (
          <button type="button" onClick={() => setExpanded((v) => !v)} className="mt-1 text-small font-semibold text-accent hover:underline">
            {expanded ? "ย่อข้อความ" : "แสดงทั้งหมด"}
          </button>
        )}
        {message.edit_proposal && <EditProposalCard edit={message.edit_proposal} onApplied={onApplied} />}
        {message.created_at && <p className={`mt-1 text-tiny text-text-muted ${mine ? "text-right" : ""}`}>{timeTh(message.created_at)} น.</p>}
      </div>
    </li>
  );
}

function Thinking() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), SLOW_MS);
    return () => clearTimeout(t);
  }, []);
  return (
    <li className="flex justify-start">
      <div className="inline-flex items-center gap-2 rounded-lg bg-primary-subtle px-4 py-3 text-small text-text-muted">
        <Loader2 className="size-4 animate-spin" strokeWidth={2} aria-hidden="true" />
        {slow ? "กำลังวิเคราะห์ อาจใช้เวลาสักครู่" : "AI กำลังตอบ…"}
      </div>
    </li>
  );
}

/**
 * @param {object} props
 * @param {(c: object) => void} [props.onCompleteness]  called with ChatResponse.completeness
 * @param {string[]} [props.suggestions]  quick replies shown while the chat is empty
 * @param {string} [props.title] @param {string} [props.subtitle]
 * @param {"tab" | "panel"} [props.variant]  tab = card on /start; panel = side panel / sheet
 * @param {() => void} [props.onReply]  called when an assistant reply arrives (unread badge)
 * @param {(result: {profile, matches}) => void} [props.onProfileChange]  after a chat edit is confirmed
 */
export function ChatPanel({ onCompleteness, onProfileChange, onReply, suggestions = [], title = "คุยเพื่อเติมข้อมูล", subtitle, variant = "tab", emptyText }) {
  const { quota } = useSession({ load: false });
  const [messages, setMessages] = useState(null);
  const [historyError, setHistoryError] = useState(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [failedText, setFailedText] = useState(null);
  const [quotaBlocked, setQuotaBlocked] = useState(null);
  const [pendingEdits, setPendingEdits] = useState([]);
  const logRef = useRef(null);
  const inputRef = useRef(null);
  const localId = useRef(0);
  const uid = useId();

  const loadHistory = useCallback(
    () =>
      data.chatHistory().then(
        (r) => {
          setHistoryError(null);
          setMessages(r.messages);
        },
        (e) => setHistoryError(e),
      ),
    [],
  );
  useEffect(() => {
    loadHistory();
    // Proposals still waiting from an earlier visit (ChatMessage has no edit_proposal).
    data.pendingEdits().then(
      (r) => setPendingEdits(r.edits),
      () => {},
    );
  }, [loadHistory]);

  // Keep the newest message in view.
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  const exhausted = quota?.exhausted || Boolean(quotaBlocked);
  const resetAt = quotaBlocked?.details?.reset_at ?? quota?.reset_at;

  async function send(raw) {
    const message = raw.trim();
    if (!message || message.length > MAX || sending || exhausted) return;
    setSending(true);
    setError(null);
    setFailedText(null);
    localId.current += 1;
    const pending = { message_id: `local-${localId.current}`, role: "user", text: message, created_at: new Date().toISOString() };
    setMessages((m) => [...(m ?? []), pending]);
    setText("");
    try {
      const res = await data.chat(message);
      setMessages((m) => [
        ...m,
        {
          message_id: res.message_id,
          role: "assistant",
          text: res.answer,
          route: res.route,
          sources: res.sources,
          edit_proposal: res.edit_proposal,
          created_at: new Date().toISOString(),
        },
      ]);
      if (res.completeness) onCompleteness?.(res.completeness);
      onReply?.();
    } catch (e) {
      // Take the unsent message back out so it can be sent again.
      setMessages((m) => m.filter((x) => x.message_id !== pending.message_id));
      if (e.code === "QUOTA_EXCEEDED") setQuotaBlocked(e);
      else {
        setError(e);
        setFailedText(message);
      }
      setText(message);
    } finally {
      setSending(false);
      refreshQuota();
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e) {
    // Enter sends, Shift+Enter is a new line; ignore Enter while a Thai IME is composing.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(text);
    }
  }

  const panel = variant === "panel";
  const counterId = `${uid}-counter`;
  const inputId = `${uid}-input`;

  return (
    <section
      aria-label={title}
      className={`flex min-h-0 flex-col ${panel ? "h-full" : "rounded-xl border border-border bg-glass p-5 shadow-sm md:p-6"}`}
    >
      <header className={panel ? "mb-3" : "mb-4"}>
        <h2 className="text-h3 font-semibold text-text">{title}</h2>
        {subtitle && <p className="mt-0.5 text-small text-text-muted">{subtitle}</p>}
      </header>

      {historyError ? (
        <ErrorState error={historyError} onRetry={loadHistory} compact />
      ) : messages === null ? (
        <LoadingBlock lines={3} label="กำลังโหลดแชท…" />
      ) : (
        <ol
          ref={logRef}
          role="log"
          aria-live="polite"
          aria-label="ข้อความในแชท"
          className={`min-h-0 flex-1 space-y-4 overflow-y-auto pr-1 ${panel ? "" : "max-h-[60vh] min-h-64"}`}
        >
          {messages.length === 0 && pendingEdits.length === 0 && (
            <li className="flex flex-col items-center rounded-lg border border-dashed border-border bg-bg px-5 py-8 text-center">
              <MessageCircle className="size-8 text-text-muted" strokeWidth={1.5} aria-hidden="true" />
              <p className="mt-3 max-w-sm text-small text-text-muted">
                {emptyText ?? "เล่าเรื่องงาน โปรเจกต์ หรือทักษะของคุณได้เลย AI จะถามต่อเฉพาะสิ่งที่ยังขาด"}
              </p>
              {suggestions.length > 0 && !exhausted && (
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      className="min-h-11 rounded-full border border-border bg-surface px-4 text-small text-text hover:border-primary"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </li>
          )}
          {messages.map((m) => (
            <Bubble key={m.message_id} message={m} onApplied={onProfileChange} />
          ))}
          {pendingEdits
            .filter((e) => !messages.some((m) => m.edit_proposal?.edit_id === e.edit_id))
            .map((e) => (
              <li key={e.edit_id} className="flex justify-start">
                <div className="max-w-[85%] rounded-lg bg-primary-subtle px-4 py-3 text-body text-text">
                  <p>ข้อเสนอแก้ไขที่ยังรอคุณยืนยัน</p>
                  <EditProposalCard edit={e} onApplied={onProfileChange} />
                </div>
              </li>
            ))}
          {sending && <Thinking />}
        </ol>
      )}

      <div className="mt-4">
        {error && (
          <div className="mb-3">
            <ErrorState error={error} onRetry={failedText ? () => send(failedText) : undefined} compact />
          </div>
        )}
        {exhausted ? (
          <p role="status" className="rounded-md border border-warning/50 bg-bg p-3 text-small text-text">
            {quotaBlocked?.messageTh ??
              `วันนี้คุณใช้โควตาถาม AI ครบแล้ว ระบบจะรีเซ็ตเวลา ${resetAt ? timeTh(resetAt) : "00:00"} น. ระหว่างนี้ยังลบทักษะหรือแก้ข้อมูลในโปรไฟล์ได้ตามปกติ`}
          </p>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(text);
            }}
          >
            <label htmlFor={inputId} className="mb-1.5 block text-small font-semibold text-text">
              ข้อความของคุณ
            </label>
            <textarea
              id={inputId}
              ref={inputRef}
              rows={panel ? 2 : 3}
              value={text}
              maxLength={MAX}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={onKeyDown}
              aria-describedby={counterId}
              placeholder="พิมพ์ข้อความ…"
              className="block w-full resize-y rounded-sm border border-border bg-bg px-3 py-2.5 text-body text-text placeholder:text-text-muted focus:border-primary focus:outline-2 focus:outline-offset-0 focus:outline-primary/30"
            />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <p id={counterId} className="text-tiny text-text-muted">
                <span className="tabular">{text.length.toLocaleString("th-TH")} / 1,000</span>
                <span className="hidden sm:inline"> · Enter ส่ง · Shift+Enter ขึ้นบรรทัดใหม่</span>
              </p>
              <Button type="submit" loading={sending} disabled={!text.trim()}>
                {!sending && <SendHorizontal className="size-4" strokeWidth={2} aria-hidden="true" />}
                ส่งข้อความ
              </Button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
