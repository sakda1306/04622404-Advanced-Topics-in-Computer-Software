"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, CheckCircle2, ExternalLink, FileWarning, Info, MinusCircle } from "lucide-react";
import { data } from "@/lib/data";
import { ProfileChangesBanner } from "@/components/app/profile-changes";
import { stepsFromWorkStyle } from "@/lib/avatar";
import { usePageReady } from "@/components/motion/page-transition";
import { useSession } from "@/lib/session";
import { StepIndicator } from "@/components/app/step-indicator";
import { EvidenceProvider } from "@/components/app/citation";
import { MatchBreakdown } from "@/components/charts/match";
import { SkillRadar } from "@/components/charts/skill-radar";
import { ChatPanel } from "@/components/chat/chat-panel";
import { WithChat } from "@/components/chat/with-chat";
import { Card, ErrorState, LevelDots, LoadingBlock } from "@/components/intake/ui";
import { RoleMarket } from "@/components/roles/role-market";
import { ExperienceNote, GapLabel, MATCH_DISCLAIMER, MatchMeter, NextSteps, StageBadge, WEIGHT_TH } from "@/components/roles/role-ui";

// Role detail /roles/[role_id] (DesignSystem.md section 4, FR-19 – FR-22):
// match summary, gaps and next steps, role description, required skill list
// (any-of groups), nice-to-have and soft skills, learning path, salary and
// market (Bangkok, with freshness), and "เกี่ยวกับข้อมูลสายงานนี้".

const THRESHOLD = 60;

/** Required skill list: one row per requirement, any-of groups joined by " / ". */
function RequiredSkills({ required, userLevels }) {
  return (
    <ul className="divide-y divide-border">
      {required.map((q, i) => {
        const have = q.skills.filter((s) => userLevels[s.skill_id]).sort((a, b) => userLevels[b.skill_id] - userLevels[a.skill_id])[0];
        const level = have ? userLevels[have.skill_id] : 0;
        const ok = level >= q.min_level;
        return (
          <li key={i} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3">
            <div className="min-w-0">
              <p className="text-small text-text">
                {q.skills.map((s, j) => (
                  <span key={s.skill_id}>
                    {j > 0 && " / "}
                    <span className={s.skill_id === have?.skill_id ? "rounded-sm bg-primary-subtle px-1 font-semibold" : ""}>{s.name_th}</span>
                  </span>
                ))}
              </p>
              {q.skills.length > 1 && <p className="text-tiny text-text-muted">มีอย่างใดอย่างหนึ่ง</p>}
            </div>
            <div className="flex items-center gap-3 text-tiny text-text-muted">
              <span className="inline-flex items-center gap-1.5" title={`ต้องการระดับ ${q.min_level}`}>
                ต้องการ <LevelDots level={q.min_level} />
                <span className="sr-only">ระดับ {q.min_level}</span>
              </span>
              <span className="rounded-full border border-border px-2 py-0.5">{WEIGHT_TH[q.weight]}</span>
              {ok ? (
                <span className="inline-flex items-center gap-1 text-success">
                  <CheckCircle2 className="size-4" strokeWidth={2} aria-hidden="true" />
                  มีแล้ว (ระดับ {level})
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-warning">
                  <MinusCircle className="size-4" strokeWidth={2} aria-hidden="true" />
                  {level ? `ต่ำกว่าระดับ (${level})` : "ยังไม่มี"}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function SkillChips({ skills, has }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {skills.map((s) => {
        const ok = has(s.skill_id);
        return (
          <li
            key={s.skill_id}
            className={`inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-small ${ok ? "border-primary/40 bg-primary-subtle text-text" : "border-border bg-bg text-text-muted"}`}
          >
            {ok ? <CheckCircle2 className="size-3.5 text-success" strokeWidth={2} aria-hidden="true" /> : <MinusCircle className="size-3.5" strokeWidth={2} aria-hidden="true" />}
            {s.name_th}
            <span className="sr-only">{ok ? " (มีแล้ว)" : " (ยังไม่มี)"}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Markdown-ish text from data/roles/<id>.md: paragraphs and numbered lines. */
function RoleText({ text }) {
  const blocks = text.split(/\n\s*\n/).filter(Boolean);
  return (
    <div className="space-y-3 text-small text-text">
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.every((l) => /^\d+\.\s/.test(l))) {
          return (
            <ol key={i} className="list-decimal space-y-1.5 pl-5">
              {lines.map((l, j) => (
                <li key={j}>{l.replace(/^\d+\.\s/, "")}</li>
              ))}
            </ol>
          );
        }
        return <p key={i}>{b}</p>;
      })}
    </div>
  );
}

export function RoleDetail() {
  const { role_id: roleId } = useParams();
  const session = useSession();
  const [state, setState] = useState({ status: "loading" });

  const load = useCallback(
    () =>
      Promise.all([data.role(roleId), data.getProfile()]).then(
        ([r, p]) => setState({ status: "ready", role: r.role, match: r.match, profile: p.profile }),
        (error) => setState({ status: "error", error }),
      ),
    [roleId],
  );

  useEffect(() => {
    if (session.status === "ready") load();
  }, [session.status, load]);
  usePageReady(session.status === "error" || state.status !== "loading");

  const hasProfile = state.status === "ready" && Boolean(state.profile);
  const page = (children) => (
    <>
      <StepIndicator current={4} unlocked={hasProfile ? 4 : 1} />
      <div className="mx-auto w-full max-w-[1120px] px-4 pt-6 pb-28 md:px-6 md:pt-8">
        <Link href="/roles" className="inline-flex min-h-11 items-center gap-1.5 rounded-md text-small font-semibold text-accent hover:underline">
          <ArrowLeft className="size-4" strokeWidth={2} aria-hidden="true" />
          กลับไปสายงานที่เหมาะ
        </Link>
        <div className="mt-2">
          <ProfileChangesBanner />
          {children}
        </div>
      </div>
    </>
  );

  if (session.status === "error") return page(<ErrorState error={session.error} onRetry={() => window.location.reload()} />);
  if (state.status === "error") return page(<ErrorState error={state.error} onRetry={state.error.code === "ROLE_NOT_FOUND" ? undefined : load} />);
  if (state.status !== "ready") return page(<LoadingBlock lines={8} label="กำลังโหลดรายละเอียดสายงาน…" />);

  const { role, match, profile } = state;
  const userLevels = Object.fromEntries((profile?.hard_skills ?? []).map((s) => [s.skill_id, s.level]));
  const softHave = new Set((profile?.soft_skills ?? []).map((s) => s.skill_id));
  const owned = new Set([...Object.keys(userLevels), ...softHave]);

  const radar = role.required.map((q, i) => ({
    key: `req-${i}`,
    label: q.skills.slice(0, 3).map((s) => s.name_th).join(" / ") + (q.skills.length > 3 ? " …" : ""),
    weight: q.weight,
    minLevel: q.min_level,
    userLevel: Math.max(0, ...q.skills.map((s) => userLevels[s.skill_id] ?? 0)),
  }));
  const niceHave = role.nice_to_have.filter((s) => userLevels[s.skill_id]).length;
  const breakdown = match && [
    { key: "hard_required", label: "ทักษะที่ต้องมี", max: 70, earned: 70 * match.breakdown.hard_required, detail: "ถ่วงน้ำหนักตามความสำคัญ" },
    { key: "hard_nice", label: "ทักษะที่ควรมี", max: 15, earned: 15 * match.breakdown.hard_nice, detail: `${niceHave} จาก ${role.nice_to_have.length} ทักษะ` },
    { key: "soft", label: "ทักษะการทำงานร่วมกับผู้อื่น", max: 10, earned: 10 * match.breakdown.soft, detail: `${role.soft_skills.filter((s) => softHave.has(s.skill_id)).length} จาก ${role.soft_skills.length} ทักษะ` },
    { key: "work_style", label: "รูปแบบการทำงาน", max: 5, earned: 5 * match.breakdown.work_style, detail: "ความใกล้เคียงของความชอบ" },
  ];

  const chat = ({ onReply }) => (
    <ChatPanel
      onReply={onReply}
      variant="panel"
      title="แชทกับ AI"
      subtitle="ถามเรื่องสายงานนี้ หรือขอแก้โปรไฟล์ · ทุกการแก้ไขต้องยืนยันก่อน"
      emptyText={`อยากรู้อะไรเกี่ยวกับสายงาน ${role.title_th} ถามได้เลย`}
      suggestions={["เงินเดือนเริ่มต้นสายนี้ประมาณเท่าไร", "ทักษะไหนของฉันเด่นที่สุด"]}
      onProfileChange={() => load()}
    />
  );

  return page(
    <EvidenceProvider evidence={profile?.evidence}>
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-h1 font-bold text-text">{role.title_th}</h1>
          <StageBadge stage={role.career_stage} />
          {role.status === "draft" && (
            <span className="inline-flex items-center gap-1 rounded-full border border-warning/60 px-2.5 py-0.5 text-tiny font-medium text-warning">
              <FileWarning className="size-3.5" strokeWidth={2} aria-hidden="true" />
              ร่าง ยังไม่ได้ตรวจทาน
            </span>
          )}
        </div>
        <p className="mt-1 font-[family-name:var(--font-latin-first)] text-body text-text-muted">{role.title_en}</p>
      </header>

      <div className="mt-6">
        <WithChat chat={chat} avatarSteps={stepsFromWorkStyle(profile?.preferences?.work_style)}>
          {match ? (
            <Card title="ความตรงกับสายงาน" subtitle={`เกณฑ์แนะนำ ${THRESHOLD}%`}>
              <MatchMeter pct={match.match_pct} threshold={THRESHOLD} size="lg" />
              <div className="mt-2">
                <ExperienceNote stage={role.career_stage} />
              </div>
              <p className="mt-3 flex items-start gap-1.5 text-tiny text-info">
                <Info className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
                {MATCH_DISCLAIMER}
              </p>
            </Card>
          ) : (
            <Card>
              <p className="text-small text-text-muted">สร้างโปรไฟล์ก่อน แล้วจะเห็นว่าคุณตรงกับสายงานนี้แค่ไหน</p>
            </Card>
          )}

          {match && (
            <div className="grid gap-6">
              {/* Full-width (landscape) cards: side by side they were too narrow and the
                  radar and bar labels were cut off. */}
              <SkillRadar roleTitle={role.title_th} skills={radar} />
              <MatchBreakdown parts={breakdown} matchPct={match.match_pct} />
            </div>
          )}

          {match && (
            <Card id="gaps" className="scroll-mt-24" title="ช่องว่างและก้าวถัดไป" subtitle="ก้าวถัดไปแต่ละข้อผูกกับช่องว่างหนึ่งข้อ">
              {match.gaps.length ? (
                <div className="grid gap-6 md:grid-cols-2">
                  <ul className="space-y-2">
                    {match.gaps.map((g) => (
                      <li key={g.gap_id}>
                        <GapLabel gap={g} />
                      </li>
                    ))}
                  </ul>
                  {match.explanations_stale ? (
                    <p className="text-small text-text-muted">คำอธิบายยังเป็นของโปรไฟล์เดิม · กด “อัปเดตคำอธิบาย” ในหน้าสายงานที่เหมาะเพื่อดูก้าวถัดไปล่าสุด</p>
                  ) : (
                    <NextSteps steps={match.next_steps} gaps={match.gaps} />
                  )}
                </div>
              ) : (
                <p className="text-small text-text">คุณมีทักษะที่สายงานนี้ต้องการครบแล้ว</p>
              )}
            </Card>
          )}

          <Card title="รายละเอียดสายงาน">
            <RoleText text={role.description_th} />
          </Card>

          <Card title="ทักษะที่ต้องมี" subtitle="ระดับ 1 เริ่มต้น · 2 ใช้งานได้ · 3 คล่อง · 4 เชี่ยวชาญ">
            <RequiredSkills required={role.required} userLevels={userLevels} />
          </Card>

          <Card title="ทักษะที่ควรมีและทักษะการทำงาน">
            <h3 className="mb-2 text-small font-semibold text-text">ทักษะที่ช่วยให้โดดเด่น (ไม่บังคับ)</h3>
            <SkillChips skills={role.nice_to_have} has={(id) => Boolean(userLevels[id])} />
            <h3 className="mt-5 mb-2 text-small font-semibold text-text">ทักษะการทำงานร่วมกับผู้อื่น</h3>
            <SkillChips skills={role.soft_skills} has={(id) => softHave.has(id)} />
          </Card>

          <Card title="เส้นทางเรียนรู้ที่แนะนำ">
            <RoleText text={role.learning_path_th} />
          </Card>

          <RoleMarket roleId={role.role_id} roleTitle={role.title_th} owned={owned} />

          <Card title="เกี่ยวกับข้อมูลสายงานนี้">
            <dl className="grid gap-x-6 gap-y-2 text-small sm:grid-cols-[max-content_1fr]">
              <dt className="text-text-muted">จัดทำโดย</dt>
              <dd className="text-text">ทีมผู้พัฒนา · {role.author}</dd>
              <dt className="text-text-muted">ผู้ตรวจทาน</dt>
              <dd className="text-text">{role.reviewer}</dd>
              <dt className="text-text-muted">สถานะ</dt>
              <dd className="text-text">{role.status === "draft" ? "ร่าง ยังไม่ได้ตรวจทาน" : "ตรวจทานแล้ว"}</dd>
              <dt className="text-text-muted">แหล่งอ้างอิง</dt>
              <dd>
                <ul className="space-y-1">
                  {role.sources.map((s) => (
                    <li key={s.url}>
                      <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all text-accent hover:underline">
                        {new URL(s.url).hostname}
                        <ExternalLink className="size-3 shrink-0" strokeWidth={2} aria-hidden="true" />
                      </a>
                      <span className="ml-1.5 text-tiny text-text-muted">({s.language === "th" ? "ภาษาไทย" : "ภาษาอังกฤษ"})</span>
                    </li>
                  ))}
                </ul>
              </dd>
            </dl>
          </Card>
        </WithChat>
      </div>
    </EvidenceProvider>,
  );
}
