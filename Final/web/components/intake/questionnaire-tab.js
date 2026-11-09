"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, ExternalLink } from "lucide-react";
import { data } from "@/lib/data";
import { Button, Card, ErrorState, LoadingBlock } from "@/components/intake/ui";
import { QuestionItem } from "@/components/intake/questions";
import {
  AVATAR_CAPTION_TH,
  AVATAR_DISCLAIMER_TH,
  AvatarProgress,
  WorkStyleAvatar,
} from "@/components/avatar/work-style-avatar";
import { stepsFromAnswers } from "@/lib/avatar";

// Questionnaire tab (FR-5 – FR-7): one section at a time, every answer saved on
// its own as soon as it changes (text after a short pause or on leaving the
// field), so the user can stop and come back later. The footer shows the O*NET
// attribution from the api (DesignSystem.md section 5).

const TEXT_DELAY = 800;

const isAnswered = (v) =>
  v !== undefined && v !== null && (Array.isArray(v) ? v.length > 0 : typeof v === "string" ? v.trim() !== "" : true);

// Live avatar beside the work-style questions (docs/WorkStyleAvatar.md section 7):
// each answer changes one part as soon as it is chosen; unanswered parts use the
// neutral stand-in and the outline stays dotted until all six are answered.
function AvatarPreview({ answers }) {
  const steps = stepsFromAnswers(answers);
  return (
    <aside className="mt-6 flex items-center gap-4 rounded-lg border border-border bg-bg p-4" aria-live="polite">
      <WorkStyleAvatar steps={steps} size={120} />
      <div className="min-w-0">
        <p className="text-small font-semibold text-text">{AVATAR_CAPTION_TH}</p>
        <p className="mt-0.5 text-small text-text-muted">แต่ละคำตอบเปลี่ยนตัวละครหนึ่งส่วน ดูคำอธิบายทุกส่วนได้ในหน้าโปรไฟล์</p>
        <AvatarProgress steps={steps} className="mt-1" />
        <p className="mt-2 text-tiny text-info">{AVATAR_DISCLAIMER_TH}</p>
      </div>
    </aside>
  );
}

function Attribution({ attribution }) {
  if (!attribution) return null;
  return (
    <footer className="mt-4 space-y-1 px-1 text-tiny text-text-muted">
      <p>{attribution.text_th}</p>
      <details>
        <summary className="inline-flex cursor-pointer items-center gap-1 font-medium text-accent hover:underline">แหล่งอ้างอิง</summary>
        <ul className="mt-2 space-y-2">
          {attribution.sources.map((s) => (
            <li key={s.url} lang="en">
              <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-accent hover:underline">
                {s.title}
                <ExternalLink className="size-3" strokeWidth={2} aria-hidden="true" />
              </a>{" "}
              ·{" "}
              <a href={s.license_url} target="_blank" rel="noreferrer" className="hover:underline">
                {s.license}
              </a>
              {s.attribution && <p className="mt-0.5">{s.attribution}</p>}
            </li>
          ))}
        </ul>
      </details>
    </footer>
  );
}

export function QuestionnaireTab({ onCompleteness }) {
  const [form, setForm] = useState(null);
  const [answers, setAnswers] = useState({});
  const [loadError, setLoadError] = useState(null);
  const [section, setSection] = useState(0);
  const [saveStates, setSaveStates] = useState({});
  const timers = useRef({});
  const latest = useRef({}); // question_id → newest request number, so stale replies are ignored
  const headingRef = useRef(null);

  // Only sets state after the requests return, so it can run inside an effect.
  const load = useCallback(async () => {
    try {
      const [q, a] = await Promise.all([data.questionnaire(), data.answers()]);
      setLoadError(null);
      setForm(q);
      setAnswers(a.answers ?? {});
      // Resume at the first section with a required question still open.
      const first = q.sections.findIndex((s) => s.questions.some((x) => !x.optional && !isAnswered(a.answers?.[x.question_id])));
      setSection(first === -1 ? 0 : first);
    } catch (e) {
      setLoadError(e);
    }
  }, []);

  useEffect(() => {
    load();
    const pending = timers.current;
    return () => Object.values(pending).forEach(clearTimeout);
  }, [load]);

  async function save(id, value) {
    const n = (latest.current[id] ?? 0) + 1;
    latest.current[id] = n;
    setSaveStates((s) => ({ ...s, [id]: "saving" }));
    try {
      const res = await data.saveAnswer(id, value);
      if (latest.current[id] !== n) return;
      setSaveStates((s) => ({ ...s, [id]: "saved" }));
      onCompleteness(res.completeness);
    } catch (e) {
      if (latest.current[id] !== n) return;
      setSaveStates((s) => ({ ...s, [id]: e }));
    }
  }

  function change(q, value) {
    setAnswers((a) => ({ ...a, [q.question_id]: value }));
    clearTimeout(timers.current[q.question_id]);
    if (q.type === "text") {
      timers.current[q.question_id] = setTimeout(() => save(q.question_id, value), TEXT_DELAY);
    } else {
      save(q.question_id, value);
    }
  }

  function flush(q) {
    if (q.type !== "text" || !timers.current[q.question_id]) return;
    clearTimeout(timers.current[q.question_id]);
    delete timers.current[q.question_id];
    save(q.question_id, answers[q.question_id] ?? "");
  }

  function retryLoad() {
    setLoadError(null);
    setForm(null);
    load();
  }

  function go(index) {
    setSection(index);
    headingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    headingRef.current?.focus({ preventScroll: true });
  }

  if (loadError) {
    return (
      <Card title="แบบสอบถาม">
        <ErrorState error={loadError} onRetry={retryLoad} />
      </Card>
    );
  }
  if (!form) {
    return (
      <Card title="แบบสอบถาม">
        <LoadingBlock lines={5} />
      </Card>
    );
  }

  const sections = form.sections;
  const current = sections[section];
  const states = Object.values(saveStates);
  const overall = states.includes("saving") ? "กำลังบันทึก…" : states.some((s) => typeof s === "object") ? "บันทึกบางข้อไม่สำเร็จ" : "บันทึกอัตโนมัติ";
  const progressOf = (s) => s.questions.filter((q) => isAnswered(answers[q.question_id])).length;

  return (
    <div>
      <Card>
        <header className="scroll-mt-24" ref={headingRef} tabIndex={-1}>
          <p className="text-small text-text-muted">
            ส่วนที่ {section + 1} / {sections.length} · {overall}
          </p>
          <h2 className="mt-0.5 text-h3 font-semibold text-text">แบบสอบถาม · {current.title_th}</h2>
        </header>

        {/* Section steps */}
        <nav aria-label="ส่วนของแบบสอบถาม" className="mt-4">
          <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {sections.map((s, i) => {
              const done = progressOf(s);
              const total = s.questions.length;
              const complete = s.questions.every((q) => q.optional || isAnswered(answers[q.question_id]));
              const isCurrent = i === section;
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => go(i)}
                    aria-current={isCurrent ? "step" : undefined}
                    className={`flex w-full flex-col gap-1.5 rounded-md border px-3 py-2 text-left transition-colors duration-150 ${
                      isCurrent ? "border-primary bg-bg" : "border-transparent hover:bg-bg"
                    }`}
                  >
                    <span className="flex items-center gap-1.5 text-tiny font-semibold text-text">
                      {complete && <Check className="size-3.5 text-success" strokeWidth={3} aria-hidden="true" />}
                      <span className="truncate">{s.title_th}</span>
                    </span>
                    <span className="h-1 overflow-hidden rounded-full bg-border" aria-hidden="true">
                      <span className="block h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${(done / total) * 100}%` }} />
                    </span>
                    <span className="sr-only">{`ตอบแล้ว ${done} จาก ${total} ข้อ`}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        {current.id === "work_style" && <AvatarPreview answers={answers} />}

        <div className="mt-6 divide-y divide-border border-t border-border pt-6">
          {current.questions.map((q) => (
            <QuestionItem
              key={q.question_id}
              q={q}
              value={answers[q.question_id]}
              onChange={(v) => change(q, v)}
              onBlur={() => flush(q)}
              saveState={saveStates[q.question_id]}
              onRetry={() => save(q.question_id, answers[q.question_id])}
            />
          ))}
        </div>

        <div className="mt-8 flex items-center justify-between gap-3 border-t border-border pt-5">
          <Button variant="secondary" onClick={() => go(section - 1)} disabled={section === 0}>
            <ArrowLeft className="size-4" strokeWidth={2} aria-hidden="true" />
            ก่อนหน้า
          </Button>
          {section < sections.length - 1 ? (
            <Button onClick={() => go(section + 1)}>
              ถัดไป
              <ArrowRight className="size-4" strokeWidth={2} aria-hidden="true" />
            </Button>
          ) : (
            <p className="text-small text-text-muted">ส่วนสุดท้ายแล้ว · ดูความครบถ้วนที่แถบด้านข้าง</p>
          )}
        </div>
      </Card>
      <Attribution attribution={form.attribution} />
    </div>
  );
}
