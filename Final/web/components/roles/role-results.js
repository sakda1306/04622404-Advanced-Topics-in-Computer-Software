"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Info, RefreshCw, SearchX, UserRound } from "lucide-react";
import { data } from "@/lib/data";
import { ProfileChangesBanner } from "@/components/app/profile-changes";
import { stepsFromWorkStyle } from "@/lib/avatar";
import { usePageReady } from "@/components/motion/page-transition";
import { refreshQuota, useSession } from "@/lib/session";
import { StepIndicator } from "@/components/app/step-indicator";
import { EvidenceProvider } from "@/components/app/citation";
import { ChatPanel } from "@/components/chat/chat-panel";
import { WithChat } from "@/components/chat/with-chat";
import { Button, ErrorState, LoadingBlock } from "@/components/intake/ui";
import { RoleMatchCard } from "@/components/roles/role-match-card";
import { GoalRoles, loadGoalRoles } from "@/components/roles/goal-roles";
import { MATCH_DISCLAIMER } from "@/components/roles/role-ui";

// Role results /roles (DesignSystem.md section 4, FR-19 – FR-20b): heading with
// the threshold, top 5 role cards, and a below-threshold banner with the closest
// roles when none pass (FR-19a). After an edit, reasons and next steps are stale
// until the user asks for new ones (that call counts toward the quota, FR-32).

function NoProfile() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center rounded-xl border border-dashed border-border bg-glass px-6 py-14 text-center">
      <UserRound className="size-10 text-text-muted" strokeWidth={1.5} aria-hidden="true" />
      <p className="mt-4 text-body text-text">ยังไม่มีโปรไฟล์ สร้างโปรไฟล์ในขั้นที่ 1 ก่อน แล้วระบบจะจับคู่สายงานให้</p>
      <Link href="/start" className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-small font-semibold text-on-primary hover:bg-primary-hover">
        ไปที่ขั้นที่ 1
        <ArrowRight className="size-4" strokeWidth={2} aria-hidden="true" />
      </Link>
    </div>
  );
}

export function RoleResults() {
  const session = useSession();
  const [state, setState] = useState({ status: "loading" });
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState(null);

  const load = useCallback(
    () =>
      Promise.all([data.matches(), data.roles(), data.getProfile()]).then(
        async ([matches, catalogue, p]) => {
          const roles = Object.fromEntries(catalogue.roles.map((r) => [r.role_id, r]));
          const goals = await loadGoalRoles(p.profile, matches, roles);
          setState({ status: "ready", matches, roles, goals, evidence: p.profile?.evidence ?? {}, workStyle: p.profile?.preferences?.work_style });
        },
        (error) => setState(error.code === "PROFILE_NOT_FOUND" ? { status: "no-profile" } : { status: "error", error }),
      ),
    [],
  );

  useEffect(() => {
    if (session.status === "ready") load();
  }, [session.status, load]);
  usePageReady(session.status === "error" || state.status !== "loading");

  async function explain() {
    setExplaining(true);
    setExplainError(null);
    try {
      const matches = await data.explainMatches();
      setState((s) => ({ ...s, matches }));
    } catch (e) {
      setExplainError(e);
    } finally {
      setExplaining(false);
      refreshQuota();
    }
  }

  const hasProfile = state.status === "ready";
  const steps = <StepIndicator current={3} unlocked={hasProfile ? 3 : 1} />;
  const page = (children) => (
    <>
      {steps}
      <div className="mx-auto w-full max-w-[1120px] px-4 pt-8 pb-28 md:px-6 md:pt-10">
        <ProfileChangesBanner />
        {children}
      </div>
    </>
  );

  if (session.status === "error") return page(<ErrorState error={session.error} onRetry={() => window.location.reload()} />);
  if (state.status === "error") return page(<ErrorState error={state.error} onRetry={load} />);
  if (state.status === "no-profile") return page(<NoProfile />);
  if (state.status !== "ready") return page(<LoadingBlock lines={8} label="กำลังจับคู่สายงาน…" />);

  const { matches, roles, goals, evidence, workStyle } = state;
  const goalIds = new Set(goals.map((g) => g.role_id));
  const stale = matches.roles.some((r) => r.explanations_stale);
  const chat = ({ onReply }) => (
    <ChatPanel
      onReply={onReply}
      variant="panel"
      title="แชทกับ AI"
      subtitle="ปรับโปรไฟล์ได้ทุกเมื่อ · ทุกการแก้ไขต้องยืนยันก่อน"
      emptyText="อยากปรับทักษะหรือเล่าประสบการณ์เพิ่มไหม AI จะเสนอการแก้ไขให้คุณตรวจสอบก่อนบันทึก"
      suggestions={["เพิ่ม Docker ระดับ 2", "เงินเดือนเริ่มต้นสายนี้ประมาณเท่าไร"]}
      onProfileChange={(r) => {
        setState((s) => ({ ...s, matches: r.matches, evidence: r.profile.evidence }));
        // Scores (and maybe the picked roles) changed, so re-read the goal roles.
        loadGoalRoles(r.profile, r.matches, roles).then((g) => setState((s) => ({ ...s, goals: g })));
      }}
    />
  );

  return page(
    <EvidenceProvider evidence={evidence}>
      <header>
        <h1 className="text-h1 font-bold text-text">สายงานที่เหมาะกับคุณ</h1>
        <p className="mt-1 text-body text-text-muted">
          {matches.below_threshold
            ? `ยังไม่มีสายงานที่ถึงเกณฑ์ ${matches.threshold}% · แสดง ${matches.roles.length} สายงานที่ใกล้ที่สุด`
            : `แสดง ${matches.roles.length} สายงานที่ตรงที่สุด จากสายงานที่ได้ตั้งแต่ ${matches.threshold}% ขึ้นไป`}
        </p>
        <p className="mt-2 flex items-start gap-1.5 text-tiny text-info">
          <Info className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
          {MATCH_DISCLAIMER}
        </p>
      </header>

      <div className="mt-6">
        <WithChat chat={chat} avatarSteps={stepsFromWorkStyle(workStyle)}>
          <GoalRoles goals={goals} threshold={matches.threshold} />

          {matches.below_threshold && (
            <div role="status" className="flex items-start gap-3 rounded-xl border border-warning/50 bg-glass p-5">
              <SearchX className="mt-0.5 size-6 shrink-0 text-warning" strokeWidth={1.75} aria-hidden="true" />
              <div>
                <p className="font-semibold text-text">ยังไม่มีสายงานที่ถึงเกณฑ์ {matches.threshold}%</p>
                <p className="mt-1 text-small text-text-muted">
                  นี่คือสายงานที่ใกล้เคียงที่สุดและสิ่งที่ยังขาด ลองเติมทักษะตามก้าวถัดไป หรือเล่าประสบการณ์เพิ่มในแชท แล้วระบบจะคำนวณใหม่ให้
                </p>
              </div>
            </div>
          )}

          {stale && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-glass p-4">
              <p className="text-small text-text">
                โปรไฟล์ของคุณเปลี่ยนแล้ว คะแนนคำนวณใหม่ให้แล้ว แต่คำอธิบายและก้าวถัดไปยังเป็นของเดิม
                <span className="block text-tiny text-text-muted">การอัปเดตคำอธิบายใช้โควตา AI 1 ครั้ง</span>
              </p>
              <Button variant="secondary" onClick={explain} loading={explaining}>
                {!explaining && <RefreshCw className="size-4" strokeWidth={2} aria-hidden="true" />}
                อัปเดตคำอธิบาย
              </Button>
            </div>
          )}
          {explainError && <ErrorState error={explainError} onRetry={explainError.code === "QUOTA_EXCEEDED" ? undefined : explain} />}

          <div className="grid gap-6 xl:grid-cols-2">
            {matches.roles.map((m) => (
              <RoleMatchCard
                key={m.role_id}
                match={m}
                role={roles[m.role_id]}
                threshold={matches.threshold}
                closest={matches.below_threshold}
                goal={goalIds.has(m.role_id)}
              />
            ))}
          </div>
        </WithChat>
      </div>
    </EvidenceProvider>,
  );
}
