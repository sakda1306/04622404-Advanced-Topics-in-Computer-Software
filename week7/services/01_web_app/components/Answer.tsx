"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { ChatEntry, Source, Trace, dateTime, routeLabels } from "../lib/types";
import { submitFeedback } from "../lib/api";
import { ErrorBox } from "./Ui";
import { useApp } from "./AppProvider";

// Work on text nodes only: code blocks and existing links are never rewritten.
export function citationPlugin({
  refs,
  prefix,
}: {
  refs: number[];
  prefix: string;
}) {
  return (tree: unknown) => {
    type Node = {
      type: string;
      value?: string;
      url?: string;
      children?: Node[];
    };
    function visit(node: Node) {
      if (!node.children || ["link", "code", "inlineCode"].includes(node.type))
        return;
      node.children = node.children.flatMap((child) => {
        if (child.type !== "text" || !child.value) {
          visit(child);
          return [child];
        }
        const parts: Node[] = [];
        let last = 0;
        for (const match of child.value.matchAll(/\[(\d+)\]/g)) {
          if (!refs.includes(Number(match[1]))) continue;
          const index = match.index!;
          if (index > last)
            parts.push({ type: "text", value: child.value.slice(last, index) });
          parts.push({
            type: "link",
            url: "#" + prefix + "-source-" + match[1],
            children: [{ type: "text", value: match[0] }],
          });
          last = index + match[0].length;
        }
        if (!last) return [child];
        if (last < child.value.length)
          parts.push({ type: "text", value: child.value.slice(last) });
        return parts;
      });
    }
    visit(tree as Node);
  };
}
export function Markdown({
  text,
  sources = [],
  prefix = "report",
}: {
  text: string;
  sources?: Source[];
  prefix?: string;
}) {
  return (
    <div className="markdown">
      <ReactMarkdown
        skipHtml
        remarkPlugins={[
          remarkGfm,
          [
            citationPlugin,
            { refs: sources.map((source) => source.ref), prefix },
          ],
        ]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ href, children }) =>
            href?.startsWith("#" + prefix + "-source-") ? (
              <a
                href={href}
                onClick={(event) => {
                  event.preventDefault();
                  const target = document.getElementById(href.slice(1));
                  target?.scrollIntoView({ block: "nearest" });
                  target?.focus();
                }}
              >
                {children}
              </a>
            ) : href && /^https?:\/\//i.test(href) ? (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ) : (
              <span>{children}</span>
            ),
          img: ({ alt }) => <span>{alt}</span>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
export function TraceView({ trace }: { trace?: Trace | null }) {
  if (!trace) return null;
  return (
    <details className="trace">
      <summary>ดูขั้นตอนการตอบ</summary>
      <dl>
        <dt>ชั้นตัดสินใจ</dt>
        <dd>{trace.decided_at_layer ?? "—"}</dd>
        <dt>หัวข้อ</dt>
        <dd>{trace.intent ?? "—"}</dd>
        <dt>การใช้ทางเลือก</dt>
        <dd>{trace.fallback ?? "ไม่มี"}</dd>
      </dl>
      {trace.rewritten_query && <p>คำค้น: {trace.rewritten_query}</p>}
      {trace.condense && (
        <p>
          การตีความคำถามต่อเนื่อง:{" "}
          {{
            applied: "ใช้บริบทจากบทสนทนา",
            unchanged: "ใช้คำถามเดิม",
            rejected: "ไม่ใช้คำถามที่ตีความใหม่",
            unavailable: "ขั้นตอนตีความไม่พร้อม ใช้คำถามเดิม",
          }[trace.condense] ?? trace.condense}
        </p>
      )}
      {trace.standalone_query && (
        <p>คำถามที่ใช้ค้นหา: {trace.standalone_query}</p>
      )}
      {trace.filters && <pre>{JSON.stringify(trace.filters, null, 2)}</pre>}
      <ol>
        {trace.steps?.map((step, index) => (
          <li key={index}>
            {step.name} <span>{step.ms} ms</span>
          </li>
        ))}
      </ol>
    </details>
  );
}
export function Answer({
  entry,
  surface = "main",
  feedback = true,
}: {
  entry: ChatEntry;
  surface?: string;
  feedback?: boolean;
}) {
  const app = useApp();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<Error>();
  const [comment, setComment] = useState("");
  const prefix = surface + "-" + entry.id;
  const hasSources = !!entry.sources?.length;
  const fallback = entry.trace?.fallback;
  const notice =
    fallback === "retrieval_down"
      ? "คลังข้อมูลไม่พร้อมใช้งานชั่วคราว จึงยังตรวจสอบข้อมูลจากคลังไม่ได้ กรุณาลองใหม่ภายหลัง"
      : fallback === "retrieval_empty" && entry.route === "football_rag"
        ? "ไม่พบข้อมูลที่ตรงกับคำถามในครั้งนี้ ลองระบุทีม ฤดูกาล หรือช่วงเวลาให้ชัดเจนขึ้น"
        : entry.route === "general_ai"
          ? "คำตอบจากความรู้ทั่วไป ไม่ได้ยืนยันด้วยข้อมูลในคลังฟุตบอล"
          : entry.route === "football_rag" && !hasSources
            ? "คำตอบนี้ไม่มีแหล่งอ้างอิงแนบมา จึงยังตรวจสอบกับข้อมูลในคลังจากหน้านี้ไม่ได้"
            : null;
  async function rate(rating: number) {
    setSaving(true);
    setError(undefined);
    try {
      await submitFeedback(entry.id, rating, comment || undefined);
      app.updateRating(entry.id, rating);
    } catch (error) {
      setError(error as Error);
    } finally {
      setSaving(false);
    }
  }
  return (
    <article className={"message " + entry.role}>
      {entry.role === "user" ? (
        <p>{entry.content}</p>
      ) : (
        <>
          <Markdown
            text={entry.content}
            sources={entry.sources}
            prefix={prefix}
          />
          {notice && <p className="answer-notice">{notice}</p>}
          {!!entry.sources?.length && (
            <ol className="sources">
              {entry.sources.map((source) => (
                <li
                  key={source.ref}
                  id={prefix + "-source-" + source.ref}
                  tabIndex={-1}
                >
                  <strong>[{source.ref}] </strong>
                  {source.url && /^https?:\/\//i.test(source.url) ? (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {source.title}
                    </a>
                  ) : (
                    source.title
                  )}
                  <small>
                    {source.origin}
                    {source.fetched_at
                      ? " · " + dateTime(source.fetched_at)
                      : ""}
                  </small>
                </li>
              ))}
            </ol>
          )}
          <div className="answer-meta">
            {entry.route && (
              <span className="badge">
                {entry.route === "football_rag" && !hasSources
                  ? "ค้นข้อมูลฟุตบอล"
                  : (routeLabels[entry.route] ?? entry.route)}
              </span>
            )}
            {entry.data_as_of && (
              <span>ข้อมูล ณ {dateTime(entry.data_as_of)}</span>
            )}
            {entry.latency_ms != null && (
              <span>{(entry.latency_ms / 1000).toFixed(1)} วินาที</span>
            )}
          </div>
          <TraceView trace={entry.trace} />
          {feedback && (
            <div className="feedback">
              <button
                disabled={saving}
                aria-label="ถูกใจคำตอบ"
                aria-pressed={entry.rating === 1}
                onClick={() => void rate(1)}
              >
                <ThumbsUp size={16} />
              </button>
              <button
                disabled={saving}
                aria-label="ไม่ถูกใจคำตอบ"
                aria-pressed={entry.rating === -1}
                onClick={() => void rate(-1)}
              >
                <ThumbsDown size={16} />
              </button>
              <details>
                <summary>เพิ่มความคิดเห็น</summary>
                <label>
                  ความคิดเห็น
                  <input
                    maxLength={1000}
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                  />
                </label>
                <small>พิมพ์แล้วกดถูกใจหรือไม่ถูกใจเพื่อส่ง</small>
              </details>
              {saving && <small role="status">กำลังบันทึก…</small>}
            </div>
          )}
          <ErrorBox error={error} />
        </>
      )}
    </article>
  );
}
