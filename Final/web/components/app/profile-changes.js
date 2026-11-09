"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { data } from "@/lib/data";
import { useSession } from "@/lib/session";

// "Your inputs changed since the profile was generated" (Contract.md Completeness.profile_changes).
// CV, questionnaire and chat answers reach the profile, and so the role matches, only when
// the profile is generated again. Removing, restoring or editing a skill on the profile or in
// chat changes the profile itself, so it never shows up here.

const LABELS = {
  cv: "CV",
  skills: "ทักษะ",
  work_style: "ความชอบในการทำงาน",
  soft_skills: "ทักษะการทำงานร่วมกับผู้อื่น",
  goals: "เป้าหมายสายงาน",
  chat: "จากแชท",
};

/** "มีการเปลี่ยนแปลงข้อมูลทักษะ", "… ข้อมูลทักษะ และ CV", "… ข้อมูล CV ทักษะ และเป้าหมายสายงาน" */
export function changedText(changes) {
  const names = changes.map((c) => LABELS[c] ?? c);
  const list = names.length < 2 ? names.join("") : `${names.slice(0, -1).join(" ")} และ${/^[A-Za-z]/.test(names.at(-1)) ? " " : ""}${names.at(-1)}`;
  // Thai runs on without a space; a Latin word such as "CV" gets one.
  return `มีการเปลี่ยนแปลงข้อมูล${/^[A-Za-z]/.test(list) ? " " : ""}${list}`;
}

/** Above the "สร้างโปรไฟล์" button on /start. */
export function ProfileChangesNote({ changes, className = "" }) {
  if (!changes?.length) return null;
  return (
    <p role="status" className={`flex items-start gap-2 rounded-md border border-warning/50 bg-warning/10 p-3 text-small text-text ${className}`}>
      <RefreshCw className="mt-0.5 size-4 shrink-0 text-warning" strokeWidth={2} aria-hidden="true" />
      <span>
        {changedText(changes)} กด “สร้างโปรไฟล์” เพื่อคำนวณสายงานที่เหมาะสมใหม่
      </span>
    </p>
  );
}

/** On the profile, roles and role pages: reads the meter itself and links back to step 1. */
export function ProfileChangesBanner() {
  const session = useSession();
  const [changes, setChanges] = useState([]);

  useEffect(() => {
    if (session.status !== "ready") return;
    data.completeness().then(
      (c) => setChanges(c.profile_changes ?? []),
      () => {}, // the page works without it
    );
  }, [session.status]);

  if (!changes.length) return null;
  return (
    <div role="status" className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-warning/50 bg-glass p-4">
      <RefreshCw className="size-5 shrink-0 text-warning" strokeWidth={2} aria-hidden="true" />
      <p className="min-w-0 flex-1 text-small text-text">
        {changedText(changes)} สร้างโปรไฟล์ใหม่เพื่อคำนวณสายงานที่เหมาะสมอีกครั้ง
      </p>
      <Link href="/start" className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-small font-semibold text-on-primary shadow-sm hover:bg-primary-hover">
        สร้างโปรไฟล์ใหม่
      </Link>
    </div>
  );
}
