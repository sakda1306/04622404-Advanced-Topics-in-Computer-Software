"use client";
import { useEffect, useRef } from "react";
import { Send, Sparkles } from "lucide-react";
import { useApp } from "./AppProvider";
import { Answer } from "./Answer";
import { SuggestedQuestions } from "./SuggestedQuestions";
import { ErrorBox, Loading } from "./Ui";
export function ChatPanel({ surface = "main" }: { surface?: string }) {
  const app = useApp(),
    textarea = useRef<HTMLTextAreaElement>(null),
    end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (app.openSignal || surface === "dock") textarea.current?.focus();
  }, [app.openSignal, surface]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [app.entries, app.pending]);
  return (
    <div className="chat-panel">
      <div
        className="chat-messages"
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
      >
        {app.historyLoading ? (
          <Loading />
        ) : (
          app.entries.length === 0 && (
            <div className="chat-welcome">
              <Sparkles size={32} />
              <h2>เรื่องฟุตบอล ถามได้เลย</h2>
              <p>
                ค้นคำตอบ พร้อมแหล่งอ้างอิง
                <br />
                จากข้อมูลของทีมที่คุณรัก
              </p>
              {surface === "dock" && <SuggestedQuestions />}
            </div>
          )
        )}
        {app.entries.map((entry) => (
          <Answer key={entry.id} entry={entry} surface={surface} />
        ))}
        {app.pending && (
          <p role="status" className="thinking">
            กำลังหาคำตอบ…
          </p>
        )}
        <div ref={end} />
      </div>
      <ErrorBox
        error={app.error}
        retry={
          app.historyTarget && !app.historyLoading
            ? () => void app.selectSession(app.historyTarget!)
            : undefined
        }
      />
      {app.historyTarget && !app.historyLoading && (
        <button onClick={app.newChat}>เริ่มแชทใหม่</button>
      )}
      <form
        className="chat-compose"
        onSubmit={(event) => {
          event.preventDefault();
          void app.sendQuestion(app.draft);
        }}
      >
        <label className="sr-only" htmlFor={surface + "-question"}>
          ถามเรื่องฟุตบอล
        </label>
        <textarea
          ref={textarea}
          id={surface + "-question"}
          rows={2}
          maxLength={2000}
          placeholder="ถามเรื่องฟุตบอล…"
          value={app.draft}
          onChange={(event) => app.setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <button
          className="primary icon-button"
          aria-label="ส่งคำถาม"
          disabled={
            app.pending ||
            app.teamBusy ||
            app.historyLoading ||
            !!app.historyTarget ||
            !app.draft.trim()
          }
        >
          <Send size={20} />
        </button>
      </form>
      <small className="compose-hint">
        {app.draft.length}/2,000 · Shift + Enter เพื่อขึ้นบรรทัดใหม่
      </small>
    </div>
  );
}
