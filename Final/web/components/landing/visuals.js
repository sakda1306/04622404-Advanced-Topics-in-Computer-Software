import { Check, FileText, Quote, TriangleAlert } from "lucide-react";
import { LogoMark } from "@/components/logo";

// Decorative previews for the landing page. Every number is labelled "ตัวอย่าง";
// none of it is user data. Glass surfaces sit on brand-gradient areas only.

function Bar({ value, className = "" }) {
  return (
    <span className={`block h-1.5 w-full overflow-hidden rounded-full bg-border ${className}`}>
      <span className="block h-full rounded-full bg-primary" style={{ width: `${value}%` }} />
    </span>
  );
}

/** Hero card: a slice of the profile, skills with evidence. */
export function ProfileCard({ className = "" }) {
  const skills = [
    { name: "ภาษา Python", value: 75 },
    { name: "SQL", value: 50 },
    { name: "การทำงานเป็นทีม", value: 90 },
  ];
  return (
    <div className={`glass w-72 rounded-xl p-5 text-left ${className}`} aria-hidden="true">
      <div className="flex items-center gap-3">
        <span className="inline-flex size-9 items-center justify-center rounded-full bg-primary-subtle text-small font-semibold text-text">
          ณ
        </span>
        <div>
          <p className="text-small font-semibold text-text">ภาพสะท้อนของคุณ</p>
          <p className="text-tiny text-text-muted">ตัวอย่าง · โปรไฟล์ที่มีหลักฐาน</p>
        </div>
      </div>
      <ul className="mt-4 space-y-3">
        {skills.map((s) => (
          <li key={s.name}>
            <span className="flex justify-between text-tiny text-text">
              <span>{s.name}</span>
              <span className="tabular text-text-muted">{s.value}%</span>
            </span>
            <Bar value={s.value} className="mt-1.5" />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Hero card: a role match result. */
export function MatchCard({ className = "" }) {
  return (
    <div className={`glass w-72 rounded-xl p-5 text-left ${className}`} aria-hidden="true">
      <div className="flex items-center justify-between">
        <span className="rounded-full bg-primary-subtle px-2.5 py-0.5 text-tiny text-text">เริ่มต้น</span>
        <LogoMark className="size-6" />
      </div>
      <p className="mt-4 text-small text-text-muted">ตรงกับสายงาน</p>
      <p className="font-[family-name:var(--font-latin-first)] text-h3 font-semibold text-text">
        Backend Developer
      </p>
      <p className="mt-3 flex items-end gap-1 font-[family-name:var(--font-latin-first)] text-accent">
        <span className="tabular text-[44px] leading-none font-semibold">78</span>
        <span className="pb-1 text-h3 font-semibold">%</span>
      </p>
      <Bar value={78} className="mt-3" />
      <p className="mt-3 text-tiny text-text-muted">ตัวอย่าง · ไม่ใช่การรับประกันการได้งาน</p>
    </div>
  );
}

/** Gradient thumbnail frame used at the top of feature and step cards. */
export function Thumb({ children, className = "" }) {
  return (
    <div className={`bg-brand-gradient relative overflow-hidden rounded-lg ${className}`} aria-hidden="true">
      <div className="hero-glow absolute -bottom-24 left-1/2 size-64 -translate-x-1/2 transition-[transform,opacity] duration-500 ease-out group-hover/feature:scale-125 group-hover/feature:opacity-100" />
      <div className="horizon absolute top-[72%] left-1/2 aspect-square w-[180%] -translate-x-1/2 rounded-full" />
      <div className="relative flex h-full items-center justify-center p-4">{children}</div>
    </div>
  );
}

export function CvPreview() {
  return (
    <div className="glass w-44 rotate-[-4deg] rounded-lg p-3 transition-[transform,box-shadow] duration-500 ease-out group-hover/feature:shadow-lg group-hover/feature:rotate-0">
      <div className="flex items-center gap-2">
        <FileText className="size-4 text-primary" strokeWidth={1.5} />
        <span className="text-tiny text-text">cv.pdf</span>
      </div>
      <span className="mt-2 block h-1.5 w-full rounded-full bg-border" />
      <span className="mt-1.5 block h-1.5 w-2/3 rounded-full bg-border" />
      <div className="mt-3 flex flex-wrap gap-1">
        {["Python", "SQL", "Git"].map((s) => (
          <span key={s} className="rounded-full bg-primary-subtle px-2 text-tiny text-text">
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}

export function EvidencePreview() {
  return (
    <div className="glass w-48 rounded-lg p-3 transition-[transform,box-shadow] duration-500 ease-out group-hover/feature:shadow-lg group-hover/feature:-rotate-2">
      <p className="flex items-center gap-1.5 text-tiny font-semibold text-text">
        <Check className="size-3.5 text-success" strokeWidth={2} />
        REST API
      </p>
      <p className="mt-2 flex gap-1.5 text-tiny text-text-muted">
        <Quote className="size-3 shrink-0 text-primary" strokeWidth={1.5} />
        “พัฒนา API สำหรับระบบจองห้อง”
      </p>
      <p className="mt-2 text-tiny text-primary">ที่มา: CV หน้า 1</p>
    </div>
  );
}

export function RolesPreview() {
  const roles = [
    { name: "Backend", value: 78 },
    { name: "Data Analyst", value: 64 },
    { name: "QA Tester", value: 58 },
  ];
  return (
    <div className="glass w-48 rounded-lg p-3 transition-[transform,box-shadow] duration-500 ease-out group-hover/feature:shadow-lg group-hover/feature:rotate-2">
      <ul className="space-y-2">
        {roles.map((r) => (
          <li key={r.name}>
            <span className="flex justify-between font-[family-name:var(--font-latin-first)] text-tiny text-text">
              {r.name}
              <span className="tabular">{r.value}%</span>
            </span>
            <Bar value={r.value} className="mt-1" />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function GapPreview() {
  return (
    <div className="glass w-48 rotate-[3deg] rounded-lg p-3 transition-[transform,box-shadow] duration-500 ease-out group-hover/feature:shadow-lg group-hover/feature:rotate-0">
      <p className="flex items-center gap-1.5 text-tiny font-semibold text-text">
        <TriangleAlert className="size-3.5 text-warning" strokeWidth={2} />
        ทักษะที่ยังขาด
      </p>
      <p className="mt-1 font-[family-name:var(--font-latin-first)] text-small font-semibold text-text">Docker</p>
      <p className="mt-1 text-tiny text-text-muted">เริ่มจากคอร์สพื้นฐาน ~1–2 สัปดาห์</p>
    </div>
  );
}
