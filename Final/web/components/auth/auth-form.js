"use client";

import { useId, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, Check, ChevronDown, Eye, EyeOff, Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { usePageTransition } from "@/components/motion/page-transition";
import { resetSession } from "@/lib/session";

// Register and Login forms on the auth endpoints (Contract.md 2.1).
// The client checks the same rules as the API first; API errors are mapped to
// a field when they belong to one, otherwise shown in the alert above the button.

// Where to go after login. The intake page (/start) opens the furthest unlocked
// step (DesignSystem.md 4.1). `?next=/path` overrides it for same-site paths only.
const AFTER_AUTH = "/start";
const MIN_PASSWORD = 8;
const MAX_NAME = 50;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const MESSAGES = {
  emailRequired: "กรุณากรอกอีเมล",
  emailFormat: "รูปแบบอีเมลไม่ถูกต้อง เช่น you@example.com",
  passwordRequired: "กรุณากรอกรหัสผ่าน",
  passwordShort: `รหัสผ่านต้องมีอย่างน้อย ${MIN_PASSWORD} ตัวอักษร`,
  passwordLong: "รหัสผ่านยาวเกินไป กรุณาใช้รหัสที่สั้นลง",
  nameRequired: "กรุณากรอกชื่อที่แสดง",
  nameLong: `ชื่อที่แสดงยาวได้ไม่เกิน ${MAX_NAME} ตัวอักษร`,
  consent: "กรุณายอมรับการใช้ข้อมูลก่อนสมัครใช้งาน",
};

// The data-use points shown under the consent checkbox (same as the landing page).
const CONSENT_POINTS = [
  "ใช้ CV คำตอบ และแชทของคุณเพื่อวิเคราะห์โปรไฟล์และแนะนำสายงานเท่านั้น",
  "ไม่เก็บข้อความใน CV ไว้ในบันทึกของระบบ",
  "ตรวจสอบ แก้ไข และลบทักษะที่ไม่ต้องการได้ตลอดเวลา",
  "ลบบัญชีและข้อมูลทั้งหมดได้จากหน้าบัญชี",
  "ผู้ดูแลระบบเห็นเฉพาะภาพรวม ไม่เห็นข้อมูลของคุณ",
];

function nextPath() {
  const next = new URLSearchParams(window.location.search).get("next");
  if (!next?.startsWith("/")) return AFTER_AUTH;
  // Let the browser read it: "/\\host" and "/\t/host" also leave the site.
  try {
    const url = new URL(next, window.location.origin);
    return url.origin === window.location.origin ? url.pathname + url.search + url.hash : AFTER_AUTH;
  } catch {
    return AFTER_AUTH;
  }
}

function validateRegister(v) {
  const e = {};
  const name = v.display_name.trim();
  if (!name) e.display_name = MESSAGES.nameRequired;
  else if (name.length > MAX_NAME) e.display_name = MESSAGES.nameLong;
  if (!v.email.trim()) e.email = MESSAGES.emailRequired;
  else if (!EMAIL_RE.test(v.email.trim())) e.email = MESSAGES.emailFormat;
  if (!v.password) e.password = MESSAGES.passwordRequired;
  else if (v.password.length < MIN_PASSWORD) e.password = MESSAGES.passwordShort;
  if (!v.consent) e.consent = MESSAGES.consent;
  return e;
}

function validateLogin(v) {
  const e = {};
  if (!v.email.trim()) e.email = MESSAGES.emailRequired;
  else if (!EMAIL_RE.test(v.email.trim())) e.email = MESSAGES.emailFormat;
  if (!v.password) e.password = MESSAGES.passwordRequired;
  return e;
}

/** Turn the API's VALIDATION_ERROR field list into Thai messages per field. */
function fieldErrorsFromApi(details) {
  const out = {};
  for (const f of details?.fields ?? []) {
    const name = String(f.field ?? "").split(".").pop();
    if (name === "email") out.email = MESSAGES.emailFormat;
    else if (name === "password") out.password = /long|bytes|at most/i.test(f.message ?? "") ? MESSAGES.passwordLong : MESSAGES.passwordShort;
    else if (name === "display_name") out.display_name = /at most|long/i.test(f.message ?? "") ? MESSAGES.nameLong : MESSAGES.nameRequired;
    else if (name === "consent") out.consent = MESSAGES.consent;
  }
  return out;
}

/* ---------- fields ---------- */

function FieldError({ id, children }) {
  if (!children) return null;
  return (
    <p id={id} className="mt-1.5 flex items-start gap-1.5 text-small text-danger">
      <AlertCircle className="mt-0.5 size-4 shrink-0" strokeWidth={2} aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

const inputClass =
  "glass-field block h-12 w-full rounded-md border px-4 text-body text-text placeholder:text-text-muted/80 transition-[border-color,box-shadow] duration-150 ease-out focus:border-primary focus:shadow-[0_0_0_4px_var(--color-primary-subtle)] focus-visible:outline-none aria-[invalid=true]:border-danger";

function TextField({ label, name, error, inputRef, hint, ...props }) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [error && errorId, hint && hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-small font-semibold text-text">
        {label}
      </label>
      <input
        ref={inputRef}
        id={id}
        name={name}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`${inputClass} border-border`}
        {...props}
      />
      {hint && !error && (
        <div id={hintId} className="mt-1.5">
          {hint}
        </div>
      )}
      <FieldError id={errorId}>{error}</FieldError>
    </div>
  );
}

function PasswordField({ label, name, error, inputRef, hint, ...props }) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const [shown, setShown] = useState(false);
  const describedBy = [error && errorId, hint && hintId].filter(Boolean).join(" ") || undefined;
  const ToggleIcon = shown ? EyeOff : Eye;
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-small font-semibold text-text">
        {label}
      </label>
      <div className="relative">
        <input
          ref={inputRef}
          id={id}
          name={name}
          type={shown ? "text" : "password"}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={`${inputClass} border-border pr-24`}
          {...props}
        />
        <button
          type="button"
          onClick={() => setShown((v) => !v)}
          aria-pressed={shown}
          aria-controls={id}
          className="absolute inset-y-1 right-1 inline-flex min-w-11 items-center gap-1.5 rounded-sm px-3 text-small text-text-muted transition-colors duration-150 ease-out hover:bg-surface hover:text-text"
        >
          <ToggleIcon className="size-4" strokeWidth={1.75} aria-hidden="true" />
          {shown ? "ซ่อน" : "แสดง"}
        </button>
      </div>
      {hint && !error && (
        <div id={hintId} className="mt-1.5">
          {hint}
        </div>
      )}
      <FieldError id={errorId}>{error}</FieldError>
    </div>
  );
}

/** "At least 8 characters" hint that ticks itself once the rule is met. */
function LengthHint({ value }) {
  const ok = value.length >= MIN_PASSWORD;
  return (
    <p className={`flex items-center gap-1.5 text-small transition-colors duration-200 ${ok ? "text-success" : "text-text-muted"}`}>
      <span
        className={`inline-flex size-4 items-center justify-center rounded-full border transition-colors duration-200 ${
          ok ? "border-success bg-success text-bg" : "border-border"
        }`}
        aria-hidden="true"
      >
        {ok && <Check className="size-3" strokeWidth={3} />}
      </span>
      อย่างน้อย {MIN_PASSWORD} ตัวอักษร
      <span className="sr-only">{ok ? " ครบแล้ว" : ""}</span>
    </p>
  );
}

function ConsentField({ checked, onChange, error, inputRef }) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div>
      <div className="flex items-start gap-3">
        <input
          ref={inputRef}
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className="mt-1 size-5 shrink-0 cursor-pointer rounded-sm accent-[var(--color-primary)]"
        />
        <label htmlFor={id} className="cursor-pointer text-small text-text">
          ฉันยินยอมให้ใช้ข้อมูลของฉันเพื่อวิเคราะห์โปรไฟล์และแนะนำสายงาน
        </label>
      </div>
      <details className="group mt-2 ml-8 text-small">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-sm font-medium text-accent hover:underline [&::-webkit-details-marker]:hidden">
          อ่านนโยบายความเป็นส่วนตัว
          <ChevronDown className="size-4 transition-transform duration-200 group-open:rotate-180" strokeWidth={2} aria-hidden="true" />
        </summary>
        <ul className="mt-2 space-y-1.5 rounded-md bg-bg/60 p-3 text-text backdrop-blur-md">
          {CONSENT_POINTS.map((p) => (
            <li key={p} className="flex items-start gap-2">
              <Check className="mt-1 size-3.5 shrink-0 text-accent" strokeWidth={2.5} aria-hidden="true" />
              {p}
            </li>
          ))}
        </ul>
      </details>
      <FieldError id={errorId}>{error}</FieldError>
    </div>
  );
}

function FormAlert({ error }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-danger/40 bg-bg/80 p-3 backdrop-blur-md text-small text-danger">
      <AlertCircle className="mt-0.5 size-5 shrink-0" strokeWidth={2} aria-hidden="true" />
      <div>
        <p className="text-text">{error.message}</p>
        {error.requestId && (
          <p className="mt-1 text-tiny text-text-muted">
            รหัสอ้างอิง: <span className="font-[family-name:var(--font-latin-first)] select-all">{error.requestId}</span>
          </p>
        )}
      </div>
    </div>
  );
}

function SubmitButton({ loading, children, loadingLabel }) {
  return (
    <button
      type="submit"
      disabled={loading}
      aria-busy={loading}
      className="group relative inline-flex h-12 w-full items-center justify-center gap-2 overflow-hidden rounded-md bg-primary px-6 text-body font-semibold text-on-primary shadow-md transition-[background-color,transform] duration-200 ease-out hover:-translate-y-0.5 hover:bg-primary-hover active:translate-y-0 disabled:cursor-wait disabled:opacity-80 disabled:hover:translate-y-0"
    >
      {/* light sweep on hover */}
      <span
        className="pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 -skew-x-12 bg-on-primary/15 opacity-0 transition-all duration-700 ease-out group-hover:left-[110%] group-hover:opacity-100"
        aria-hidden="true"
      />
      {loading ? (
        <>
          <Loader2 className="size-5 animate-spin" strokeWidth={2} aria-hidden="true" />
          {loadingLabel}
        </>
      ) : (
        <>
          {children}
          <ArrowRight className="size-5 transition-transform duration-200 ease-out group-hover:translate-x-1" strokeWidth={2} aria-hidden="true" />
        </>
      )}
    </button>
  );
}

/* ---------- shared form logic ---------- */

// `success(values)` gives the {message, detail} shown on the transition panel
// while the next page loads.
function useAuthForm({ initial, validate, order, submit, success }) {
  const router = useRouter();
  const { navigate } = usePageTransition();
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const refs = useRef({});

  function set(name, value) {
    const next = { ...values, [name]: value };
    setValues(next);
    // After the first submit, re-check as the user types so errors clear early.
    if (submitted) setErrors(validate(next));
  }

  function focusFirst(errs) {
    const first = order.find((name) => errs[name]);
    if (first) refs.current[first]?.focus();
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (loading) return;
    setSubmitted(true);
    setFormError(null);
    const errs = validate(values);
    setErrors(errs);
    if (Object.keys(errs).length) {
      focusFirst(errs);
      return;
    }

    setLoading(true);
    try {
      await submit(values);
      // The landing page may have recorded "signed out"; read the new session fresh.
      resetSession();
      navigate(nextPath(), { replace: true, kind: "success", ...success(values) });
      router.refresh();
    } catch (error) {
      setLoading(false);
      if (!(error instanceof ApiError)) {
        setFormError({ message: "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง" });
        return;
      }
      if (error.code === "VALIDATION_ERROR") {
        const fieldErrs = fieldErrorsFromApi(error.details);
        if (Object.keys(fieldErrs).length) {
          setErrors(fieldErrs);
          focusFirst(fieldErrs);
          return;
        }
      }
      if (error.code === "EMAIL_TAKEN") {
        setErrors({ email: error.messageTh });
        focusFirst({ email: true });
        return;
      }
      const showId = !["INVALID_CREDENTIALS", "RATE_LIMITED", "NETWORK_ERROR"].includes(error.code);
      setFormError({ message: error.messageTh, requestId: showId ? error.requestId : undefined });
    }
  }

  const bind = (name) => ({
    inputRef: (el) => (refs.current[name] = el),
    error: errors[name],
  });

  return { values, set, onSubmit, loading, formError, bind };
}

/* ---------- forms ---------- */

export function RegisterForm() {
  const { values, set, onSubmit, loading, formError, bind } = useAuthForm({
    initial: { display_name: "", email: "", password: "", consent: false },
    validate: validateRegister,
    order: ["display_name", "email", "password", "consent"],
    submit: (v) =>
      api("/auth/register", {
        method: "POST",
        body: {
          display_name: v.display_name.trim(),
          email: v.email.trim(),
          password: v.password,
          consent: true,
        },
      }),
    success: (v) => ({ message: "สมัครสมาชิกสำเร็จ", detail: `ยินดีต้อนรับ ${v.display_name.trim()}` }),
  });

  return (
    <form onSubmit={onSubmit} noValidate className="mt-6 space-y-5">
      <TextField
        label="ชื่อที่แสดง"
        name="display_name"
        autoComplete="nickname"
        placeholder="กมล"
        maxLength={MAX_NAME}
        value={values.display_name}
        onChange={(e) => set("display_name", e.target.value)}
        {...bind("display_name")}
      />
      <TextField
        label="อีเมล"
        name="email"
        type="email"
        inputMode="email"
        autoComplete="email"
        spellCheck={false}
        placeholder="you@example.com"
        value={values.email}
        onChange={(e) => set("email", e.target.value)}
        {...bind("email")}
      />
      <PasswordField
        label="รหัสผ่าน"
        name="password"
        autoComplete="new-password"
        value={values.password}
        onChange={(e) => set("password", e.target.value)}
        hint={<LengthHint value={values.password} />}
        {...bind("password")}
      />
      <ConsentField checked={values.consent} onChange={(v) => set("consent", v)} {...bind("consent")} />
      <FormAlert error={formError} />
      <SubmitButton loading={loading} loadingLabel="กำลังสร้างบัญชี…">
        สมัครใช้งาน
      </SubmitButton>
      <p className="text-center text-small text-text">
        มีบัญชีแล้ว?{" "}
        <Link href="/login" className="rounded-sm font-semibold text-accent underline-offset-4 hover:underline">
          เข้าสู่ระบบ
        </Link>
      </p>
    </form>
  );
}

export function LoginForm() {
  const { values, set, onSubmit, loading, formError, bind } = useAuthForm({
    initial: { email: "", password: "" },
    validate: validateLogin,
    order: ["email", "password"],
    submit: (v) => api("/auth/login", { method: "POST", body: { email: v.email.trim(), password: v.password } }),
    success: () => ({ message: "เข้าสู่ระบบสำเร็จ", detail: "ยินดีต้อนรับกลับ" }),
  });

  return (
    <form onSubmit={onSubmit} noValidate className="mt-6 space-y-5">
      <TextField
        label="อีเมล"
        name="email"
        type="email"
        inputMode="email"
        autoComplete="email"
        spellCheck={false}
        placeholder="you@example.com"
        value={values.email}
        onChange={(e) => set("email", e.target.value)}
        {...bind("email")}
      />
      <PasswordField
        label="รหัสผ่าน"
        name="password"
        autoComplete="current-password"
        value={values.password}
        onChange={(e) => set("password", e.target.value)}
        {...bind("password")}
      />
      <FormAlert error={formError} />
      <SubmitButton loading={loading} loadingLabel="กำลังเข้าสู่ระบบ…">
        เข้าสู่ระบบ
      </SubmitButton>
      <p className="text-center text-small text-text">
        ยังไม่มีบัญชี?{" "}
        <Link href="/register" className="rounded-sm font-semibold text-accent underline-offset-4 hover:underline">
          สมัครใช้งาน
        </Link>
      </p>
    </form>
  );
}
