"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Briefcase,
  CheckCircle2,
  FileText,
  Pencil,
  Plus,
  Trash2,
  Upload,
  Wrench,
  X,
} from "lucide-react";
import { data } from "@/lib/data";
import { Button, Card, ErrorState, LevelDots, LevelPicker, LoadingBlock, levelLabel } from "@/components/intake/ui";

// CV tab (DesignSystem.md section 3: File upload, Parsed CV review; FR-0 – FR-4).
// idle → uploading (progress) → draft review (edit, remove, add) → confirmed.
// Errors use the api's message_th: CV_INVALID_TYPE, CV_TOO_LARGE, CV_UNREADABLE.

const MAX_BYTES = 5 * 1024 * 1024;
const LOCAL_ERRORS = {
  type: { code: "CV_INVALID_TYPE", messageTh: "ไฟล์นี้ไม่ใช่ PDF กรุณาอัปโหลดไฟล์ .pdf ขนาดไม่เกิน 5 MB" },
  size: { code: "CV_TOO_LARGE", messageTh: "ไฟล์ใหญ่เกิน 5 MB กรุณาลดขนาดไฟล์แล้วลองใหม่" },
};

let keySeq = 0;
const withKeys = (items) => items.map((it) => ({ ...it, _key: `k${(keySeq += 1)}` }));
const stripKeys = (items) =>
  items.map(({ _key, ...rest }) => Object.fromEntries(Object.entries(rest).filter(([, v]) => v !== "" && v !== undefined && v !== null)));

const period = (start, end) => [start, end].filter(Boolean).join(" – ");

/* ---------- upload ---------- */

function Dropzone({ onFile, disabled }) {
  const inputRef = useRef(null);
  const hintId = useId();
  const [dragging, setDragging] = useState(false);

  function pick(files) {
    const file = files?.[0];
    if (file) onFile(file);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!disabled) pick(e.dataTransfer.files);
      }}
      className={`relative flex flex-col items-center rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors duration-150 ${
        dragging ? "border-primary bg-primary-subtle" : "border-border bg-bg"
      }`}
    >
      <span
        className={`inline-flex size-14 items-center justify-center rounded-full transition-transform duration-200 ${
          dragging ? "-translate-y-1 bg-primary text-on-primary" : "bg-primary-subtle text-primary"
        }`}
      >
        <Upload className="size-6" strokeWidth={1.75} aria-hidden="true" />
      </span>
      <p className="mt-4 text-h3 font-semibold text-text">{dragging ? "วางไฟล์ได้เลย" : "ลากไฟล์มาวางที่นี่ หรือเลือกไฟล์"}</p>
      <p id={hintId} className="mt-1 text-small text-text-muted">
        PDF ไม่เกิน 5 MB · ไฟล์ต้องคัดลอกข้อความได้ (ไม่ใช่ไฟล์สแกน)
      </p>
      <Button className="mt-5" onClick={() => inputRef.current?.click()} disabled={disabled} aria-describedby={hintId}>
        <FileText className="size-4" strokeWidth={1.75} aria-hidden="true" />
        เลือกไฟล์ PDF
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => {
          pick(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function UploadProgress({ filename, progress }) {
  const parsing = progress >= 1;
  return (
    <div className="rounded-lg border border-border bg-bg p-5" role="status" aria-live="polite">
      <div className="flex items-center gap-3">
        <FileText className="size-8 shrink-0 text-primary" strokeWidth={1.5} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-small font-semibold text-text">{filename}</p>
          <p className="text-tiny text-text-muted">{parsing ? "กำลังอ่านทักษะ การศึกษา และประสบการณ์…" : `กำลังอัปโหลด ${Math.round(progress * 100)}%`}</p>
        </div>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-border">
        <div
          className={`h-full rounded-full bg-primary transition-[width] duration-300 ease-out ${parsing ? "animate-pulse" : ""}`}
          style={{ width: `${Math.max(4, progress * 100)}%` }}
        />
      </div>
    </div>
  );
}

/* ---------- review ---------- */

const fieldClass =
  "block h-11 w-full rounded-md border border-border bg-bg px-3 text-small text-text placeholder:text-text-muted focus:border-primary focus-visible:outline-none focus:shadow-[0_0_0_3px_var(--color-primary-subtle)]";

function Field({ label, value, onChange, placeholder, error, multiline = false, required = false }) {
  const id = useId();
  const Tag = multiline ? "textarea" : "input";
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-tiny font-semibold text-text">
        {label}
        {!required && <span className="font-normal text-text-muted"> (ไม่บังคับ)</span>}
      </label>
      <Tag
        id={id}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        className={`${fieldClass} ${multiline ? "h-auto min-h-20 py-2" : ""} aria-[invalid=true]:border-danger`}
        rows={multiline ? 3 : undefined}
      />
      {error && <p className="mt-1 text-tiny text-danger">{error}</p>}
    </div>
  );
}

function GroupHeader({ Icon, title, count, onAdd, addLabel }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border pb-2">
      <h3 className="inline-flex items-center gap-2 text-small font-semibold text-text">
        <Icon className="size-4 text-accent" strokeWidth={1.75} aria-hidden="true" />
        {title}
        <span className="tabular rounded-full bg-bg px-2 text-tiny font-medium text-text-muted">{count}</span>
      </h3>
      <button type="button" onClick={onAdd} className="inline-flex min-h-9 items-center gap-1 rounded-md px-2 text-small font-semibold text-accent hover:bg-bg">
        <Plus className="size-4" strokeWidth={2} aria-hidden="true" />
        {addLabel}
      </button>
    </div>
  );
}

function RowActions({ onEdit, onRemove, editLabel, removeLabel }) {
  return (
    <div className="flex shrink-0 gap-1">
      {onEdit && (
        <button type="button" onClick={onEdit} aria-label={editLabel} className="inline-flex size-9 items-center justify-center rounded-md text-text-muted hover:bg-bg hover:text-text">
          <Pencil className="size-4" strokeWidth={1.75} aria-hidden="true" />
        </button>
      )}
      <button type="button" onClick={onRemove} aria-label={removeLabel} className="inline-flex size-9 items-center justify-center rounded-md text-text-muted hover:bg-bg hover:text-danger">
        <Trash2 className="size-4" strokeWidth={1.75} aria-hidden="true" />
      </button>
    </div>
  );
}

function SkillRows({ skills, setSkills }) {
  const [adding, setAdding] = useState("");
  const addRef = useRef(null);
  const update = (key, patch) => setSkills(skills.map((s) => (s._key === key ? { ...s, ...patch } : s)));

  function add(e) {
    e.preventDefault();
    const name = adding.trim();
    if (!name) return;
    setSkills([...skills, ...withKeys([{ name, line_no: 0 }])]);
    setAdding("");
  }

  return (
    <div>
      <GroupHeader Icon={Wrench} title="ทักษะ" count={skills.length} addLabel="เพิ่มทักษะ" onAdd={() => addRef.current?.focus()} />
      <ul className="divide-y divide-border">
        {skills.map((s) => (
          <li key={s._key} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
            <div className="min-w-40 flex-1">
              <p className="font-semibold text-text">{s.name}</p>
              {s.level ? (
                <p className="mt-0.5 inline-flex items-center gap-2 text-small text-text-muted">
                  <LevelDots level={s.level} />
                  ระดับ {s.level} · {levelLabel(s.level)}
                </p>
              ) : (
                <p className="mt-0.5 inline-flex items-center gap-1.5 text-small font-medium text-warning">
                  <AlertTriangle className="size-3.5" strokeWidth={2} aria-hidden="true" />
                  ยังไม่ระบุระดับ
                </p>
              )}
            </div>
            <LevelPicker size="sm" label={`ระดับของ ${s.name}`} value={s.level} onChange={(level) => update(s._key, { level })} />
            <RowActions onRemove={() => setSkills(skills.filter((x) => x._key !== s._key))} removeLabel={`ลบทักษะ ${s.name}`} />
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="mt-2 flex gap-2">
        <label className="sr-only" htmlFor="cv-add-skill">
          ชื่อทักษะที่ต้องการเพิ่ม
        </label>
        <input
          ref={addRef}
          id="cv-add-skill"
          value={adding}
          onChange={(e) => setAdding(e.target.value)}
          placeholder="เพิ่มทักษะ เช่น Docker"
          maxLength={100}
          className={fieldClass}
        />
        <Button type="submit" variant="secondary" disabled={!adding.trim()} aria-label="เพิ่มทักษะที่พิมพ์">
          เพิ่ม
        </Button>
      </form>
    </div>
  );
}

function EntryRows({ kind, items, setItems }) {
  const isExp = kind === "experience";
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState(null);
  const mainKey = isExp ? "title" : "school";

  function start(item) {
    setEditing(item?._key ?? "new");
    setDraft(item ? { ...item } : { [mainKey]: "", line_no: 0 });
    setError(null);
  }

  function saveDraft() {
    if (!draft[mainKey]?.trim()) {
      setError(isExp ? "กรุณากรอกชื่อตำแหน่งหรือโปรเจกต์" : "กรุณากรอกชื่อสถานศึกษา");
      return;
    }
    const clean = { ...draft, [mainKey]: draft[mainKey].trim() };
    setItems(editing === "new" ? [...items, ...withKeys([clean])] : items.map((it) => (it._key === editing ? clean : it)));
    setEditing(null);
  }

  const set = (field) => (value) => setDraft((d) => ({ ...d, [field]: value }));

  const form = draft && (
    <div className="my-3 space-y-3 rounded-lg border border-border bg-bg p-4">
      {isExp ? (
        <>
          <Field label="ตำแหน่ง หรือชื่อโปรเจกต์" required value={draft.title} onChange={set("title")} error={error} placeholder="เช่น นักศึกษาฝึกงาน Backend" />
          <Field label="บริษัท หรือที่มา" value={draft.company} onChange={set("company")} placeholder="เช่น โปรเจกต์รายวิชา" />
        </>
      ) : (
        <>
          <Field label="สถานศึกษา" required value={draft.school} onChange={set("school")} error={error} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="วุฒิ" value={draft.degree} onChange={set("degree")} placeholder="เช่น ปริญญาตรี" />
            <Field label="สาขา" value={draft.field} onChange={set("field")} placeholder="เช่น วิศวกรรมคอมพิวเตอร์" />
          </div>
        </>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="เริ่ม" value={draft.start} onChange={set("start")} placeholder="เช่น 2567" />
        <Field label="สิ้นสุด" value={draft.end} onChange={set("end")} placeholder="เช่น 2568 หรือ ปัจจุบัน" />
      </div>
      {isExp && <Field label="สิ่งที่ทำ" multiline value={draft.summary} onChange={set("summary")} />}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => setEditing(null)}>
          ยกเลิก
        </Button>
        <Button onClick={saveDraft}>บันทึก</Button>
      </div>
    </div>
  );

  return (
    <div>
      <GroupHeader
        Icon={isExp ? Briefcase : BookOpen}
        title={isExp ? "ประสบการณ์" : "การศึกษา"}
        count={items.length}
        addLabel={isExp ? "เพิ่มประสบการณ์" : "เพิ่มการศึกษา"}
        onAdd={() => start(null)}
      />
      {items.length === 0 && editing !== "new" && (
        <p className="py-3 text-small text-text-muted">
          {isExp ? "ไม่พบประสบการณ์ในไฟล์ เพิ่มเองได้ หรือบอกในแบบสอบถามว่ายังไม่มีประสบการณ์" : "ไม่พบประวัติการศึกษาในไฟล์"}
        </p>
      )}
      <ul className="divide-y divide-border">
        {items.map((it) =>
          editing === it._key ? (
            <li key={it._key}>{form}</li>
          ) : (
            <li key={it._key} className="flex items-start gap-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-text">{it[mainKey]}</p>
                <p className="mt-0.5 text-small text-text-muted">
                  {[isExp ? it.company : [it.degree, it.field].filter(Boolean).join(" "), period(it.start, it.end)].filter(Boolean).join(" · ")}
                </p>
                {isExp && it.summary && <p className="mt-1 text-small text-text">{it.summary}</p>}
              </div>
              <RowActions
                onEdit={() => start(it)}
                onRemove={() => setItems(items.filter((x) => x._key !== it._key))}
                editLabel={`แก้ไข ${it[mainKey]}`}
                removeLabel={`ลบ ${it[mainKey]}`}
              />
            </li>
          ),
        )}
      </ul>
      {editing === "new" && form}
    </div>
  );
}

function CvReview({ cv, onConfirmed, onCancel }) {
  const [skills, setSkills] = useState(() => withKeys(cv.skills));
  const [experience, setExperience] = useState(() => withKeys(cv.experience));
  const [education, setEducation] = useState(() => withKeys(cv.education));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const unrated = skills.filter((s) => !s.level).length;

  async function confirm() {
    setSaving(true);
    setError(null);
    try {
      const res = await data.confirmCv({ skills: stripKeys(skills), experience: stripKeys(experience), education: stripKeys(education) });
      onConfirmed(res);
    } catch (e) {
      setError(e);
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      {cv.warnings_th?.length > 0 && (
        <ul className="space-y-1 rounded-md border border-warning/50 bg-bg p-3 text-small text-text">
          {cv.warnings_th.map((w) => (
            <li key={w} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" strokeWidth={2} aria-hidden="true" />
              {w}
            </li>
          ))}
        </ul>
      )}
      <SkillRows skills={skills} setSkills={setSkills} />
      <EntryRows kind="experience" items={experience} setItems={setExperience} />
      <EntryRows kind="education" items={education} setItems={setEducation} />

      <div className="space-y-3 border-t border-border pt-5">
        {unrated > 0 && (
          <p className="text-small text-text-muted">
            ทักษะที่ยังไม่ระบุระดับ {unrated} รายการจะยังไม่นับในความครบถ้วน
          </p>
        )}
        <ErrorState error={error} compact />
        <div className="flex flex-wrap gap-3">
          <Button className="flex-1" loading={saving} onClick={confirm}>
            <CheckCircle2 className="size-4" strokeWidth={1.75} aria-hidden="true" />
            ยืนยันข้อมูล
          </Button>
          {onCancel && (
            <Button variant="secondary" onClick={onCancel} disabled={saving}>
              ยกเลิกการแก้ไข
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------- confirmed ---------- */

function CvConfirmed({ cv, onEdit, onReplace, onDelete }) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);

  async function remove() {
    setDeleting(true);
    setError(null);
    try {
      await onDelete();
    } catch (e) {
      setError(e);
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 rounded-lg bg-primary-subtle p-4">
        <CheckCircle2 className="size-6 shrink-0 text-success" strokeWidth={1.75} aria-hidden="true" />
        <p className="text-small text-text">
          ยืนยันข้อมูลแล้ว ระบบใช้ข้อมูลนี้คำนวณความครบถ้วน และใช้สร้างโปรไฟล์ในขั้นถัดไป
        </p>
      </div>
      <div>
        <p className="text-small font-semibold text-text">ทักษะ {cv.skills.length} รายการ</p>
        <ul className="mt-2 flex flex-wrap gap-2">
          {cv.skills.map((s) => (
            <li key={`${s.name}-${s.line_no}`} className="inline-flex items-center gap-2 rounded-full border border-border bg-bg px-3 py-1 text-small text-text">
              {s.name}
              {s.level ? <LevelDots level={s.level} /> : <span className="text-tiny text-warning">ไม่มีระดับ</span>}
              <span className="sr-only">{s.level ? `ระดับ ${s.level}` : "ยังไม่ระบุระดับ"}</span>
            </li>
          ))}
        </ul>
      </div>
      <dl className="grid gap-3 text-small sm:grid-cols-2">
        <div className="rounded-md bg-bg p-3">
          <dt className="text-text-muted">ประสบการณ์</dt>
          <dd className="mt-0.5 font-semibold text-text">{cv.experience.length ? `${cv.experience.length} รายการ` : "ไม่มี"}</dd>
        </div>
        <div className="rounded-md bg-bg p-3">
          <dt className="text-text-muted">การศึกษา</dt>
          <dd className="mt-0.5 font-semibold text-text">{cv.education[0]?.school ?? "ไม่มี"}</dd>
        </div>
      </dl>

      <ErrorState error={error} compact />
      <div className="flex flex-wrap gap-2 border-t border-border pt-5">
        <Button variant="secondary" onClick={onEdit}>
          <Pencil className="size-4" strokeWidth={1.75} aria-hidden="true" />
          แก้ไขข้อมูล
        </Button>
        <Button variant="secondary" onClick={() => fileRef.current?.click()}>
          <Upload className="size-4" strokeWidth={1.75} aria-hidden="true" />
          อัปโหลดไฟล์ใหม่
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) onReplace(f);
          }}
        />
        <div className="ml-auto">
          {confirmDelete ? (
            <div className="flex items-center gap-2" role="group" aria-label="ยืนยันการลบ CV">
              <span className="text-small text-text">ลบ CV และข้อมูลที่มาจาก CV เท่านั้น?</span>
              <Button variant="danger" loading={deleting} onClick={remove}>
                ลบ
              </Button>
              <Button variant="ghost" onClick={() => setConfirmDelete(false)} disabled={deleting} aria-label="ยกเลิกการลบ">
                <X className="size-4" strokeWidth={2} aria-hidden="true" />
              </Button>
            </div>
          ) : (
            <Button variant="ghost" className="text-danger" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="size-4" strokeWidth={1.75} aria-hidden="true" />
              ลบ CV
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------- tab ---------- */

export function CvTab({ onCompleteness, onGoToQuestionnaire }) {
  const [phase, setPhase] = useState("loading"); // loading | empty | uploading | review | confirmed | load-error
  const [cv, setCv] = useState(null);
  const [upload, setUpload] = useState({ filename: "", progress: 0 });
  const [error, setError] = useState(null);

  // Only sets state after the request returns, so it can run inside an effect.
  const load = useCallback(
    () =>
      data.getCv().then(
        (res) => {
          setError(null);
          setCv(res.cv);
          setPhase(!res.cv ? "empty" : res.cv.status === "confirmed" ? "confirmed" : "review");
        },
        (e) => {
          setError(e);
          setPhase("load-error");
        },
      ),
    [],
  );

  useEffect(() => {
    load();
  }, [load]);

  function retryLoad() {
    setPhase("loading");
    setError(null);
    load();
  }

  async function uploadFile(file) {
    setError(null);
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) return setError(LOCAL_ERRORS.type);
    if (file.size > MAX_BYTES) return setError(LOCAL_ERRORS.size);
    const previous = phase;
    setUpload({ filename: file.name, progress: 0 });
    setPhase("uploading");
    try {
      const res = await data.uploadCv(file, (progress) => setUpload((u) => ({ ...u, progress })));
      setCv(res.cv);
      setPhase("review");
    } catch (e) {
      setError(e);
      setPhase(previous === "confirmed" ? "confirmed" : "empty");
    }
  }

  const subtitle = {
    review: cv && `${cv.filename} · อ่านสำเร็จ · กรุณาตรวจสอบและยืนยันก่อนใช้`,
    confirmed: cv && `${cv.filename} · ยืนยันแล้ว`,
  }[phase] ?? "PDF ไม่เกิน 5 MB · ตรวจสอบก่อนนำไปสร้างโปรไฟล์";

  return (
    <Card title={phase === "review" ? "ตรวจสอบข้อมูลจาก CV" : phase === "confirmed" ? "ข้อมูลจาก CV" : "เพิ่ม CV ของคุณ"} subtitle={subtitle}>
      <div className="space-y-4">
        {phase !== "review" && error && (
          <div className="space-y-2">
            <ErrorState error={error} onRetry={phase === "load-error" ? retryLoad : undefined} />
            {error.code === "CV_UNREADABLE" && (
              <button type="button" onClick={onGoToQuestionnaire} className="text-small font-semibold text-accent underline-offset-4 hover:underline">
                ไปทำแบบสอบถามแทน →
              </button>
            )}
          </div>
        )}
        {phase === "loading" && <LoadingBlock lines={3} />}
        {phase === "empty" && (
          <>
            <Dropzone onFile={uploadFile} />
            <ul className="space-y-1 px-1 text-small text-text-muted">
              <li>เราจะอ่านทักษะ การศึกษา และประสบการณ์จากไฟล์</li>
              <li>คุณแก้ไขหรือลบข้อมูลที่อ่านได้ก่อนยืนยันได้ · ไม่มี CV ก็ใช้แบบสอบถามแทนได้</li>
            </ul>
          </>
        )}
        {phase === "uploading" && <UploadProgress {...upload} />}
        {phase === "review" && cv && (
          <CvReview
            key={`${cv.filename}-${cv.status}`}
            cv={cv}
            onCancel={cv.status === "confirmed" ? () => setPhase("confirmed") : undefined}
            onConfirmed={(res) => {
              setCv(res.cv);
              onCompleteness(res.completeness);
              setPhase("confirmed");
            }}
          />
        )}
        {phase === "confirmed" && cv && (
          <CvConfirmed
            cv={cv}
            onEdit={() => setPhase("review")}
            onReplace={uploadFile}
            onDelete={async () => {
              const res = await data.deleteCv();
              onCompleteness(res.completeness);
              setCv(null);
              setPhase("empty");
            }}
          />
        )}
      </div>
    </Card>
  );
}
