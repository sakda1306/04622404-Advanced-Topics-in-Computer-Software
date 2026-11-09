"use client";

import { useId, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, Loader2, Plus, RotateCcw, Search, X } from "lucide-react";
import { LevelPicker, levelLabel } from "@/components/intake/ui";

// Questionnaire items (DesignSystem.md section 3, Questionnaire item): single,
// multi (with max_choices), scale 1-5 with end labels, skill checklist with
// level, and text. Each item shows its own save state (auto-save, FR-6).

const LOCATION_NOTE = "ข้อมูลตำแหน่งงานและเงินเดือนในแอปมีเฉพาะกรุงเทพฯ";
const TEXT_MAX = 1000;

export function SaveState({ state, onRetry }) {
  if (!state) return null;
  if (state === "saving")
    return (
      <span className="inline-flex items-center gap-1 text-tiny text-text-muted">
        <Loader2 className="size-3.5 animate-spin" strokeWidth={2} aria-hidden="true" />
        กำลังบันทึก
      </span>
    );
  if (state === "saved")
    return (
      <span className="inline-flex items-center gap-1 text-tiny text-success">
        <Check className="size-3.5" strokeWidth={3} aria-hidden="true" />
        บันทึกแล้ว
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 text-tiny text-danger">
      <AlertTriangle className="size-3.5" strokeWidth={2} aria-hidden="true" />
      {state.messageTh ?? "บันทึกไม่สำเร็จ"}
      {onRetry && (
        <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 font-semibold text-accent hover:underline">
          <RotateCcw className="size-3" strokeWidth={2} aria-hidden="true" />
          ลองใหม่
        </button>
      )}
    </span>
  );
}

const optionBase =
  "flex min-h-12 cursor-pointer items-center gap-3 rounded-md border px-4 py-2 text-small transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary";
const optionState = (checked, disabled) =>
  checked
    ? "border-primary bg-primary-subtle text-text"
    : disabled
      ? "cursor-not-allowed border-border bg-bg text-text-muted opacity-60"
      : "border-border bg-bg text-text hover:border-primary";

// Wraps the first match of any search token in a highlight; plain text otherwise.
function Highlight({ text, tokens }) {
  if (!tokens?.length) return text;
  const lower = text.toLowerCase();
  let best = null;
  for (const t of tokens) {
    const i = lower.indexOf(t);
    if (i >= 0 && (!best || i < best[0])) best = [i, t.length];
  }
  if (!best) return text;
  const [i, n] = best;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded-sm bg-transparent font-bold text-accent underline decoration-2 underline-offset-2">{text.slice(i, i + n)}</mark>
      {text.slice(i + n)}
    </>
  );
}

// Thai label, then the English name when the api sends one (role options, Contract v0.3f).
function OptionLabel({ option, tokens }) {
  if (!option.label_en) return <Highlight text={option.label_th} tokens={tokens} />;
  return (
    <span>
      <Highlight text={option.label_th} tokens={tokens} />
      <span className="text-text-muted" lang="en">
        {" · "}
        <Highlight text={option.label_en} tokens={tokens} />
      </span>
    </span>
  );
}

function Single({ q, value, onChange }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {q.options.map((o) => {
        const checked = value === o.value;
        return (
          <label key={o.value} className={`${optionBase} ${optionState(checked)}`}>
            <input type="radio" name={q.question_id} value={o.value} checked={checked} onChange={() => onChange(o.value)} className="sr-only" />
            <span className={`inline-flex size-5 shrink-0 items-center justify-center rounded-full border-2 ${checked ? "border-primary" : "border-border"}`} aria-hidden="true">
              {checked && <span className="size-2.5 rounded-full bg-primary" />}
            </span>
            {o.label_th}
          </label>
        );
      })}
    </div>
  );
}

// Long option lists (the 26 IT roles) get a search box. A search never hides an
// option: matches are highlighted and the first one scrolls into view.
const SEARCH_FROM = 9;

// Short words people type for a role, mapped to words in the role names.
const SEARCH_ALIASES = {
  dev: ["developer", "นักพัฒนา"],
  eng: ["engineer", "วิศวกร"],
  ml: ["machine learning", "ml engineer"],
  ai: ["ai", "ปัญญาประดิษฐ์"],
  qa: ["qa", "tester", "ทดสอบ"],
  test: ["qa", "ทดสอบ"],
  db: ["database", "ฐานข้อมูล"],
  pm: ["project manager", "ผู้จัดการโครงการ"],
  security: ["security", "ความปลอดภัย"],
  ux: ["ux", "ui"],
  ui: ["ui", "ux"],
  web: ["web", "เว็บ"],
  front: ["frontend", "front-end"],
  back: ["backend", "back-end"],
};

const tokensOf = (query) => query.toLowerCase().split(/\s+/).filter(Boolean);

function haystack(o) {
  return [o.label_th, o.label_en, o.value.replace(/-/g, " "), o.value].filter(Boolean).join(" ").toLowerCase();
}

/** Every token must match the option text, directly or through an alias. */
function matches(o, tokens) {
  const text = haystack(o);
  return tokens.every((t) => text.includes(t) || (SEARCH_ALIASES[t] ?? []).some((a) => text.includes(a)));
}

function Multi({ q, value = [], onChange }) {
  const max = q.max_choices;
  const full = max !== undefined && value.length >= max;
  const searchable = q.options.length >= SEARCH_FROM;
  const [query, setQuery] = useState("");
  const searchId = useId();
  const optionRefs = useRef({});
  const tokens = useMemo(() => tokensOf(query), [query]);
  const hits = useMemo(() => (tokens.length ? q.options.filter((o) => matches(o, tokens)) : []), [q.options, tokens]);
  const hitSet = new Set(hits.map((o) => o.value));
  const toggle = (v) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);

  function search(next) {
    setQuery(next);
    const first = tokensOf(next).length ? q.options.find((o) => matches(o, tokensOf(next))) : null;
    if (first) requestAnimationFrame(() => optionRefs.current[first.value]?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  }

  function onSearchKey(e) {
    if (e.key === "Escape" && query) {
      e.preventDefault();
      search("");
    }
    if (e.key !== "Enter") return;
    e.preventDefault();
    const first = hits[0];
    if (first && (value.includes(first.value) || !full)) toggle(first.value);
  }

  const chosen = q.options.filter((o) => value.includes(o.value));

  return (
    <div>
      {max && (
        <p className="mb-2 text-tiny text-text-muted" aria-live="polite">
          เลือกได้ไม่เกิน {max} ข้อ · เลือกแล้ว <span className="tabular">{value.length}</span>
        </p>
      )}

      {searchable && (
        <div className="mb-3 space-y-2">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-text-muted" strokeWidth={2} aria-hidden="true" />
            <input
              id={searchId}
              type="search"
              value={query}
              onChange={(e) => search(e.target.value)}
              onKeyDown={onSearchKey}
              placeholder="ค้นหาสายงาน เช่น data, dev, นักพัฒนา"
              aria-label="ค้นหาสายงาน"
              aria-describedby={`${searchId}-status`}
              className="h-11 w-full rounded-md border border-border bg-bg pr-10 pl-10 text-small text-text placeholder:text-text-muted focus:border-primary focus:shadow-[0_0_0_4px_var(--color-primary-subtle)] focus-visible:outline-none [&::-webkit-search-cancel-button]:hidden"
            />
            {query && (
              <button
                type="button"
                onClick={() => search("")}
                aria-label="ล้างคำค้นหา"
                className="absolute top-1/2 right-1.5 inline-flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-text-muted hover:bg-surface hover:text-text"
              >
                <X className="size-4" strokeWidth={2} aria-hidden="true" />
              </button>
            )}
          </div>
          <p id={`${searchId}-status`} className="min-h-[18px] text-tiny text-text-muted" aria-live="polite">
            {tokens.length === 0
              ? "พิมพ์เพื่อไฮไลต์สายงานที่ตรง · กด Enter เพื่อเลือกอันแรก"
              : hits.length
                ? `พบ ${hits.length} สายงาน · กด Enter เพื่อเลือก “${hits[0].label_th}”`
                : `ไม่พบสายงานที่ตรงกับ “${query.trim()}” · ลองค้นหา “data” หรือ “dev”`}
          </p>
          {chosen.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-tiny font-semibold text-text-muted">เลือกแล้ว</span>
              {chosen.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => toggle(o.value)}
                  className="inline-flex min-h-8 items-center gap-1 rounded-full bg-primary px-2.5 text-tiny font-semibold text-on-primary hover:bg-primary-hover"
                >
                  {o.label_th}
                  <X className="size-3.5" strokeWidth={2.5} aria-hidden="true" />
                  <span className="sr-only">นำออก</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {q.options.map((o) => {
          const checked = value.includes(o.value);
          const disabled = !checked && full;
          const hit = hitSet.has(o.value);
          return (
            <label
              key={o.value}
              ref={(el) => (optionRefs.current[o.value] = el)}
              className={`${optionBase} min-h-11 rounded-full py-1.5 transition-[transform,box-shadow,border-color,background-color] duration-200 ease-out ${optionState(checked, disabled)} ${
                hit ? "scale-[1.04] border-accent shadow-md ring-2 ring-accent ring-offset-2 ring-offset-surface" : ""
              }`}
            >
              <input type="checkbox" checked={checked} disabled={disabled} onChange={() => toggle(o.value)} className="sr-only" />
              {checked && <Check className="size-4 text-primary" strokeWidth={2.5} aria-hidden="true" />}
              <OptionLabel option={o} tokens={hit ? tokens : null} />
            </label>
          );
        })}
      </div>
    </div>
  );
}

function Scale({ q, value, onChange }) {
  const { min, max, min_label_th, max_label_th } = q.scale;
  const points = Array.from({ length: max - min + 1 }, (_, i) => min + i);
  const minId = useId();
  const maxId = useId();
  return (
    <div>
      <div role="radiogroup" aria-describedby={`${minId} ${maxId}`} className="grid grid-cols-5 gap-2">
        {points.map((p) => {
          const checked = value === p;
          return (
            <label
              key={p}
              className={`flex min-h-12 cursor-pointer items-center justify-center rounded-md border text-body font-semibold tabular transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary ${
                checked ? "border-primary bg-primary text-on-primary" : "border-border bg-bg text-text hover:border-primary"
              }`}
            >
              <input type="radio" name={q.question_id} value={p} checked={checked} onChange={() => onChange(p)} className="sr-only" />
              {p}
            </label>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between gap-4 text-tiny text-text-muted">
        <span id={minId}>{min} = {min_label_th}</span>
        <span id={maxId} className="text-right">{max} = {max_label_th}</span>
      </div>
    </div>
  );
}

function TextAnswer({ q, value = "", onChange, onBlur }) {
  const id = useId();
  return (
    <div>
      <textarea
        aria-labelledby={`${q.question_id}-label`}
        id={id}
        value={value}
        maxLength={TEXT_MAX}
        rows={4}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder="เช่น ตอนทำโปรเจกต์จบ ฉันเป็นคนประสานงานกับอาจารย์และแบ่งงานในทีม…"
        className="block w-full rounded-md border border-border bg-bg px-4 py-3 text-body text-text placeholder:text-text-muted focus:border-primary focus-visible:outline-none focus:shadow-[0_0_0_3px_var(--color-primary-subtle)]"
      />
      <p className="mt-1 text-right text-tiny text-text-muted tabular">
        {value.length}/{TEXT_MAX}
      </p>
    </div>
  );
}

// Common picks shown before the user searches (only those in the option list).
const SUGGESTED = ["python", "javascript", "sql", "java", "git", "react", "html-css", "linux", "docker", "excel"];

function SkillChecklist({ q, value = [], onChange }) {
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState([]); // added but no level yet: not sent until rated
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listId = useId();

  const labels = useMemo(() => Object.fromEntries(q.options.map((o) => [o.value, o.label_th])), [q.options]);
  const chosen = new Set([...value.map((v) => v.skill_id), ...pending]);
  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return [];
    return q.options
      .filter((o) => !chosen.has(o.value) && (o.label_th.toLowerCase().includes(term) || o.value.includes(term)))
      .slice(0, 8);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, q.options, value, pending]);
  const suggestions = SUGGESTED.filter((id) => labels[id] && !chosen.has(id));

  function add(id) {
    setPending((p) => [...p, id]);
    setQuery("");
    setActive(0);
    inputRef.current?.focus();
  }

  function setLevel(id, level) {
    setPending((p) => p.filter((x) => x !== id));
    const rest = value.filter((v) => v.skill_id !== id);
    const existing = value.find((v) => v.skill_id === id);
    onChange(existing ? value.map((v) => (v.skill_id === id ? { ...v, level } : v)) : [...rest, { skill_id: id, level }]);
  }

  function remove(id) {
    if (pending.includes(id)) setPending((p) => p.filter((x) => x !== id));
    else onChange(value.filter((v) => v.skill_id !== id));
  }

  function onKeyDown(e) {
    if (!matches.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % matches.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + matches.length) % matches.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      add(matches[active].value);
    } else if (e.key === "Escape") {
      setQuery("");
    }
  }

  const rows = [...value.map((v) => ({ id: v.skill_id, level: v.level })), ...pending.map((id) => ({ id, level: undefined }))];
  const rated = value.length;

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-text-muted" strokeWidth={1.75} aria-hidden="true" />
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded={matches.length > 0}
          aria-controls={listId}
          aria-activedescendant={matches.length ? `${listId}-${active}` : undefined}
          aria-autocomplete="list"
          aria-label="ค้นหาทักษะ"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          placeholder="ค้นหาทักษะ เช่น Python, SQL, Docker"
          className="block h-12 w-full rounded-md border border-border bg-bg pr-4 pl-10 text-body text-text placeholder:text-text-muted focus:border-primary focus-visible:outline-none focus:shadow-[0_0_0_3px_var(--color-primary-subtle)]"
        />
        {matches.length > 0 && (
          <ul id={listId} role="listbox" aria-label="ทักษะที่ตรงกับคำค้น" className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border border-border bg-bg p-1 shadow-md">
            {matches.map((o, i) => (
              <li
                key={o.value}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onPointerDown={(e) => {
                  e.preventDefault();
                  add(o.value);
                }}
                onPointerEnter={() => setActive(i)}
                className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-sm px-3 text-small ${i === active ? "bg-surface text-text" : "text-text"}`}
              >
                <Plus className="size-4 text-accent" strokeWidth={2} aria-hidden="true" />
                {o.label_th}
              </li>
            ))}
          </ul>
        )}
        {query.trim() && matches.length === 0 && (
          <p className="mt-1 text-tiny text-text-muted">ไม่พบทักษะนี้ในรายการ ลองคำอื่น หรือเล่าเพิ่มในแชท</p>
        )}
      </div>

      {suggestions.length > 0 && (
        <div>
          <p className="mb-2 text-tiny text-text-muted">ทักษะที่พบบ่อย</p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => add(id)}
                className="inline-flex min-h-9 items-center gap-1 rounded-full border border-dashed border-border px-3 text-small text-text hover:border-primary hover:bg-bg"
              >
                <Plus className="size-3.5 text-accent" strokeWidth={2} aria-hidden="true" />
                {labels[id]}
              </button>
            ))}
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <ul className="divide-y divide-border rounded-lg border border-border bg-bg">
          {rows.map(({ id, level }) => (
            <li key={id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
              <div className="min-w-36 flex-1">
                <p className="text-small font-semibold text-text">{labels[id] ?? id}</p>
                <p className={`text-tiny ${level ? "text-text-muted" : "font-medium text-warning"}`}>
                  {level ? `ระดับ ${level} · ${levelLabel(level)}` : "เลือกระดับเพื่อบันทึก"}
                </p>
              </div>
              <LevelPicker size="sm" label={`ระดับของ ${labels[id] ?? id}`} value={level} onChange={(l) => setLevel(id, l)} />
              <button
                type="button"
                onClick={() => remove(id)}
                aria-label={`เอา ${labels[id] ?? id} ออก`}
                className="inline-flex size-9 items-center justify-center rounded-md text-text-muted hover:bg-surface hover:text-danger"
              >
                <X className="size-4" strokeWidth={2} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-tiny text-text-muted" aria-live="polite">
        เลือกแล้ว <span className="tabular">{rated}</span> ทักษะพร้อมระดับ {rated < 3 && "· ต้องมีอย่างน้อย 3 ทักษะ"} · ระดับ 1 เริ่มต้น → 4 เชี่ยวชาญ
      </p>
    </div>
  );
}

export function QuestionItem({ q, value, onChange, onBlur, saveState, onRetry }) {
  const labelId = `${q.question_id}-label`;
  const Input = { single: Single, multi: Multi, scale: Scale, skill_checklist: SkillChecklist, text: TextAnswer }[q.type];
  const grouped = q.type === "single" || q.type === "multi";
  const body = Input ? <Input q={q} value={value} onChange={onChange} onBlur={onBlur} /> : null;
  return (
    <div className="py-6 first:pt-0 last:pb-0">
      {grouped ? (
        <fieldset aria-labelledby={labelId}>
          <QuestionHeader q={q} labelId={labelId} saveState={saveState} onRetry={onRetry} />
          {body}
        </fieldset>
      ) : (
        <div role="group" aria-labelledby={labelId}>
          <QuestionHeader q={q} labelId={labelId} saveState={saveState} onRetry={onRetry} />
          {body}
        </div>
      )}
      {q.question_id === "go_location" && <p className="mt-2 text-small text-info">{LOCATION_NOTE}</p>}
    </div>
  );
}

function QuestionHeader({ q, labelId, saveState, onRetry }) {
  return (
    <div className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
      <p id={labelId} className="max-w-prose font-semibold text-text">
        {q.text_th}
        {q.optional && <span className="font-normal text-text-muted"> (ไม่บังคับ)</span>}
      </p>
      <span className="min-h-5" aria-live="polite">
        <SaveState state={saveState} onRetry={onRetry} />
      </span>
    </div>
  );
}
