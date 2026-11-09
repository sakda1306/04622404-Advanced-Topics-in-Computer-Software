"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Code2, Handshake, RotateCcw, UserRound, X } from "lucide-react";
import { data } from "@/lib/data";
import { ProfileChangesBanner } from "@/components/app/profile-changes";
import { stepsFromWorkStyle } from "@/lib/avatar";
import { usePageReady } from "@/components/motion/page-transition";
import { dateTh } from "@/lib/format";
import { useSession } from "@/lib/session";
import { StepIndicator } from "@/components/app/step-indicator";
import { EvidenceProvider } from "@/components/app/citation";
import { ConfirmDialog } from "@/components/app/confirm-dialog";
import { ChatPanel } from "@/components/chat/chat-panel";
import { WithChat } from "@/components/chat/with-chat";
import { ErrorState, LoadingBlock } from "@/components/intake/ui";
import { SkillLevels } from "@/components/profile/skill-levels";
import { Tile } from "@/components/app/bento";
import {
  BlindSpotsTile,
  CharacterTile,
  EvidenceTile,
  ExperienceTile,
  KpiTiles,
  LevelMixTile,
  SkillStrengthTile,
  StrengthCard,
  TraitsTile,
} from "@/components/profile/profile-dashboard";

// Profile page /profile (DesignSystem.md section 4, FR-15 – FR-17, FR-29 – FR-33):
// hard skills, soft skills, work style (with disclaimer), experience and blind
// spots. Every claim cites its evidence inline [n]; skill chips can be removed
// (confirm first, no LLM call, works with no quota) and restored. The chat stays
// beside the profile: a side panel at lg, a bottom sheet below lg.

/** Skill chips grouped by level, with remove (a bento tile). */
function SkillSection({ title, subtitle, icon, skills, empty, onRemove, busy, tone }) {
  return (
    <Tile title={title} icon={icon} className="lg:col-span-2">
      <p className="-mt-2 mb-4 text-tiny text-text-muted">{subtitle}</p>
      {skills.length ? (
        <SkillLevels skills={skills} tone={tone} onRemove={onRemove} busy={busy} label={title} />
      ) : (
        <p className="text-small text-text-muted">{empty}</p>
      )}
    </Tile>
  );
}

function RemovedSkills({ skills, onRestore, busy }) {
  if (!skills.length) return null;
  return (
    <Tile title="ทักษะที่คุณลบออก" icon={RotateCcw} className="md:col-span-2 lg:col-span-4">
      <p className="-mt-2 mb-2 text-tiny text-text-muted">ไม่นำมาใช้คำนวณสายงาน · กู้คืนได้ทุกเมื่อ</p>
      <ul className="divide-y divide-border">
        {skills.map((s) => (
          <li key={s.skill_id} className="flex items-center justify-between gap-3 py-2">
            <span className="text-small text-text">
              {s.name_th}
              <span className="ml-2 text-tiny text-text-muted">ลบเมื่อ {dateTh(s.removed_at)}</span>
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={() => onRestore(s)}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-3 text-small font-semibold text-accent hover:bg-bg disabled:opacity-50"
            >
              <RotateCcw className="size-4" strokeWidth={2} aria-hidden="true" />
              กู้คืน
            </button>
          </li>
        ))}
      </ul>
    </Tile>
  );
}

function Toast({ toast, onClose }) {
  useEffect(() => {
    if (!toast || toast.kind === "error") return;
    const t = setTimeout(onClose, 5000);
    return () => clearTimeout(t);
  }, [toast, onClose]);
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex justify-center px-4 lg:bottom-6">
      {toast && (
        <div className="pointer-events-auto flex items-center gap-3 rounded-lg border border-border bg-glass px-4 py-3 text-small text-text shadow-lg">
          <span>{toast.text}</span>
          {toast.action && (
            <button type="button" onClick={toast.action.run} className="min-h-9 rounded-md px-2 font-semibold text-accent hover:bg-bg">
              {toast.action.label}
            </button>
          )}
          <button type="button" onClick={onClose} aria-label="ปิด" className="inline-flex size-9 items-center justify-center rounded-md text-text-muted hover:bg-bg">
            <X className="size-4" strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      )}
    </div>
  );
}

function EmptyProfile() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center rounded-xl border border-dashed border-border bg-glass px-6 py-14 text-center">
      <UserRound className="size-10 text-text-muted" strokeWidth={1.5} aria-hidden="true" />
      <p className="mt-4 text-body text-text">ยังไม่มีโปรไฟล์ เริ่มจากอัปโหลด CV หรือทำแบบสอบถาม</p>
      <Link href="/start" className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-small font-semibold text-on-primary hover:bg-primary-hover">
        ไปที่ขั้นที่ 1
        <ArrowRight className="size-4" strokeWidth={2} aria-hidden="true" />
      </Link>
    </div>
  );
}

export function Profile() {
  const session = useSession();
  const [profile, setProfile] = useState(undefined); // undefined = loading, null = none yet
  const [removed, setRemoved] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [confirming, setConfirming] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [toast, setToast] = useState(null);

  const load = useCallback(
    () =>
      Promise.all([data.getProfile(), data.removedSkills().catch(() => ({ skills: [] }))]).then(
        ([p, r]) => {
          setLoadError(null);
          setProfile(p.profile);
          setRemoved(r.skills);
        },
        (e) => {
          if (e.code === "PROFILE_NOT_FOUND") setProfile(null);
          else setLoadError(e);
        },
      ),
    [],
  );

  useEffect(() => {
    if (session.status === "ready") load();
  }, [session.status, load]);
  usePageReady(session.status === "error" || profile !== undefined || Boolean(loadError));

  const closeToast = useCallback(() => setToast(null), []);

  async function restore(skill) {
    setBusy(true);
    setActionError(null);
    try {
      const r = await data.restoreSkill(skill.skill_id);
      setProfile(r.profile);
      setRemoved((list) => list.filter((s) => s.skill_id !== skill.skill_id));
      setToast({ text: `กู้คืน ${skill.name_th} แล้ว` });
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    const skill = confirming;
    setBusy(true);
    setActionError(null);
    try {
      const r = await data.removeSkill(skill.skill_id);
      setProfile(r.profile);
      setRemoved((list) => [...list.filter((s) => s.skill_id !== skill.skill_id), { skill_id: skill.skill_id, name_th: skill.name_th, removed_at: new Date().toISOString() }]);
      setConfirming(null);
      setToast({ text: `ลบ ${skill.name_th} ออกจากโปรไฟล์แล้ว`, action: { label: "เลิกทำ", run: () => restore(skill) } });
    } catch (e) {
      setConfirming(null);
      setActionError(e);
    } finally {
      setBusy(false);
    }
  }

  const ready = session.status === "ready" && profile;
  const steps = <StepIndicator current={2} unlocked={profile ? 3 : 1} />;
  const wrap = (children) => (
    <>
      {steps}
      <div className="mx-auto w-full max-w-[1120px] px-4 pt-8 pb-28 md:px-6 md:pt-10">
        <ProfileChangesBanner />
        {children}
      </div>
    </>
  );

  if (session.status === "error") return wrap(<ErrorState error={session.error} onRetry={() => window.location.reload()} />);
  if (loadError) return wrap(<ErrorState error={loadError} onRetry={load} />);
  if (session.status !== "ready" || profile === undefined) return wrap(<LoadingBlock lines={8} label="กำลังโหลดโปรไฟล์…" />);
  if (!ready) return wrap(<EmptyProfile />);

  const chat = ({ onReply }) => (
    <ChatPanel
      onReply={onReply}
      variant="panel"
      title="แชทกับ AI"
      subtitle="ถามหรือขอแก้โปรไฟล์ได้ · ทุกการแก้ไขต้องยืนยันก่อน · ใช้โควตาครั้งละ 1"
      emptyText="อยากรู้อะไรเพิ่มเกี่ยวกับโปรไฟล์นี้ ถามได้เลย"
      suggestions={["ทักษะไหนของฉันเด่นที่สุด", "เปลี่ยนระดับ SQL เป็น 3"]}
      onProfileChange={(r) => {
        setProfile(r.profile);
        data.removedSkills().then((x) => setRemoved(x.skills), () => {});
      }}
    />
  );

  return wrap(
    <EvidenceProvider evidence={profile.evidence}>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-h1 font-bold text-text">ภาพสะท้อนทักษะของคุณ</h1>
          <p className="mt-1 text-body text-text-muted">
            สร้างเมื่อ {dateTh(profile.generated_at)}
            {profile.updated_at !== profile.generated_at && ` · แก้ไขล่าสุด ${dateTh(profile.updated_at)}`} · ทุกข้อมูลมีหลักฐานกำกับ [n] กดเพื่อดูที่มา
          </p>
        </div>
        <Link href="/roles" className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-5 text-small font-semibold text-on-primary shadow-sm hover:bg-primary-hover">
          ดูสายงานที่เหมาะ
          <ArrowRight className="size-4" strokeWidth={2} aria-hidden="true" />
        </Link>
      </header>

      {actionError && (
        <div className="mt-6">
          <ErrorState error={actionError} />
        </div>
      )}

      <div className="mt-6">
        <WithChat chat={chat} avatarSteps={stepsFromWorkStyle(profile.preferences?.work_style)}>
          {/* Like the reference: a grid of charts on the left, a column for the character on the right. */}
          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <KpiTiles profile={profile} />
              <SkillStrengthTile skills={profile.hard_skills} />
              <TraitsTile workStyle={profile.work_style} values={profile.preferences?.work_style} />
              <LevelMixTile hard={profile.hard_skills} soft={profile.soft_skills} />
              <BlindSpotsTile claims={profile.blind_spots} />
              <StrengthCard profile={profile} />
              <ExperienceTile experience={profile.experience} />
            </div>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1">
              <CharacterTile workStyle={profile.work_style} values={profile.preferences?.work_style} />
              <EvidenceTile profile={profile} />
            </div>
          </div>
          <div className="grid items-start gap-4 md:grid-cols-2 lg:grid-cols-4">
            <SkillSection
              title="จัดการทักษะด้านเทคนิค"
              icon={Code2}
              subtitle={`${profile.hard_skills.length} ทักษะ · จัดกลุ่มตามระดับ · กด × เพื่อลบทักษะที่ไม่ใช่ของคุณ`}
              skills={profile.hard_skills}
              tone="tech"
              empty="ยังไม่มีทักษะด้านเทคนิค เพิ่มได้จาก CV แบบสอบถาม หรือแชท"
              onRemove={setConfirming}
              busy={busy}
            />
            <SkillSection
              title="จัดการทักษะการทำงานร่วมกับผู้อื่น"
              icon={Handshake}
              subtitle={`${profile.soft_skills.length} ทักษะ · จากคะแนนที่คุณให้ตัวเอง 4–5 และตัวอย่างที่เล่า`}
              skills={profile.soft_skills}
              tone="team"
              empty="ยังไม่มีหลักฐานทักษะด้านนี้ เล่าตัวอย่างในแชทได้"
              onRemove={setConfirming}
              busy={busy}
            />
            <RemovedSkills skills={removed} onRestore={restore} busy={busy} />
          </div>
        </WithChat>
      </div>

      <ConfirmDialog
        open={Boolean(confirming)}
        title={confirming ? `ลบ ${confirming.name_th} ออกจากโปรไฟล์?` : ""}
        confirmLabel="ลบทักษะ"
        danger
        loading={busy}
        onConfirm={remove}
        onCancel={() => setConfirming(null)}
      >
        ทักษะนี้จะไม่ถูกนำไปคำนวณสายงานที่เหมาะ และจะไม่ถูกเพิ่มกลับเองเมื่อสร้างโปรไฟล์ใหม่ คุณกู้คืนได้ทุกเมื่อจากรายการ “ทักษะที่คุณลบออก” หรือหน้าบัญชี
      </ConfirmDialog>

      <Toast toast={toast} onClose={closeToast} />
    </EvidenceProvider>,
  );
}
