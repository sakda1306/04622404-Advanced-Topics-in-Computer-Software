"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, ClipboardList, FileText, MessageCircle, ShieldCheck } from "lucide-react";
import { StepIndicator } from "@/components/app/step-indicator";
import { ChatPanel } from "@/components/chat/chat-panel";
import { ProfileChangesNote } from "@/components/app/profile-changes";
import { data } from "@/lib/data";
import { usePageReady, usePageTransition } from "@/components/motion/page-transition";
import { stepsFromAnswers, stepsFromWorkStyle } from "@/lib/avatar";
import { refreshQuota, useSession } from "@/lib/session";
import { Card, ErrorState, LoadingBlock } from "@/components/intake/ui";
import { CompletenessPanel, THRESHOLD } from "@/components/intake/completeness-panel";
import { CvTab } from "@/components/intake/cv-tab";
import { QuestionnaireTab } from "@/components/intake/questionnaire-tab";

// Intake page /start (DesignSystem.md section 2 and 4): tabs CV / แบบสอบถาม /
// แชท in any order, and the progress sidebar (320 px, sticky at lg; a
// collapsible score bar above the content below lg).

const TABS = [
  { id: "cv", label: "CV", Icon: FileText },
  { id: "questionnaire", label: "แบบสอบถาม", Icon: ClipboardList },
  { id: "chat", label: "แชท", Icon: MessageCircle },
];

function Tabs({ tab, onChange }) {
  const refs = useRef([]);
  function onKeyDown(e, i) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step && e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    const next = e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : (i + step + TABS.length) % TABS.length;
    refs.current[next]?.focus();
    onChange(TABS[next].id);
  }
  return (
    <div role="tablist" aria-label="วิธีเพิ่มข้อมูล" className="grid grid-cols-3 gap-2 rounded-lg border border-border bg-glass p-1">
      {TABS.map(({ id, label, Icon }, i) => {
        const selected = tab === id;
        return (
          <button
            key={id}
            ref={(el) => (refs.current[i] = el)}
            role="tab"
            id={`tab-${id}`}
            aria-selected={selected}
            aria-controls={`panel-${id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-3 text-small font-semibold transition-colors duration-150 ${
              selected ? "bg-primary text-on-primary shadow-sm" : "text-text-muted hover:bg-bg hover:text-text"
            }`}
          >
            <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
            {label}
          </button>
        );
      })}
    </div>
  );
}

function PrivacyCard() {
  return (
    <Card>
      <div className="flex gap-4">
        <ShieldCheck className="size-6 shrink-0 text-accent" strokeWidth={1.5} aria-hidden="true" />
        <div>
          <h2 className="font-semibold text-text">ข้อมูลของคุณอยู่ในการควบคุมของคุณ</h2>
          <p className="mt-1 text-small text-text-muted">ใช้เพื่อวิเคราะห์โปรไฟล์และแนะนำสายงานเท่านั้น · ลบข้อมูลทั้งหมดได้ในหน้าบัญชี</p>
        </div>
      </div>
    </Card>
  );
}

export function Intake() {
  const router = useRouter();
  const transition = usePageTransition();
  const params = useSearchParams();
  const session = useSession();
  const tab = TABS.some((t) => t.id === params.get("tab")) ? params.get("tab") : "cv";

  const [completeness, setCompleteness] = useState(null);
  const [completenessError, setCompletenessError] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState(null);
  const [hasProfile, setHasProfile] = useState(false);

  // State is set only in the promise callbacks, so this can run inside an effect.
  const loadCompleteness = useCallback(
    () =>
      data.completeness().then(
        (c) => {
          setCompletenessError(null);
          setCompleteness(c);
        },
        (e) => setCompletenessError(e),
      ),
    [],
  );

  useEffect(() => {
    if (session.status !== "ready") return;
    loadCompleteness();
    // Steps 2 and 3 unlock once a profile exists; a failure just keeps them locked.
    data.getProfile().then(
      (r) => setHasProfile(Boolean(r.profile)),
      () => {},
    );
  }, [session.status, loadCompleteness]);

  usePageReady(session.status === "error" || (session.status === "ready" && Boolean(completeness || completenessError)));

  const setTab = (id) => router.replace(`/start?tab=${id}`, { scroll: false });

  // The transition panel covers the page while the profile is generated and stays
  // up until /profile has loaded. The character is built from the saved answers
  // while the request runs, then from the generated profile.
  async function generate() {
    setGenerating(true);
    setGenerateError(null);
    transition.show({ kind: "generate", stage: 0 });
    let generated = false;
    data.answers().then(
      (r) => !generated && transition.update({ steps: stepsFromAnswers(r.answers) }),
      () => {},
    );
    try {
      const r = await data.generateProfile();
      generated = true;
      refreshQuota();
      transition.update({ stage: 1, steps: stepsFromWorkStyle(r.profile?.preferences?.work_style) });
      transition.navigate("/profile", { kind: "generate", stage: 1 });
      // Next keeps this page mounted (hidden) for the back button, so reset the
      // button; the transition panel covers the page until /profile is ready.
      setGenerating(false);
      setHasProfile(true);
    } catch (e) {
      transition.cancel();
      setGenerateError(e);
      setGenerating(false);
      if (e.code === "PROFILE_NOT_READY") loadCompleteness();
    }
  }

  const steps = <StepIndicator current={1} unlocked={hasProfile ? 3 : 1} />;

  if (session.status === "error") {
    return (
      <>
        {steps}
        <div className="mx-auto w-full max-w-[1120px] px-4 py-10 md:px-6">
          <ErrorState error={session.error} onRetry={() => window.location.reload()} />
        </div>
      </>
    );
  }
  if (session.status !== "ready") {
    return (
      <>
        {steps}
        <div className="mx-auto w-full max-w-[1120px] px-4 py-10 md:px-6">
          <LoadingBlock lines={6} label="กำลังโหลดข้อมูลของคุณ…" />
        </div>
      </>
    );
  }

  const panel = (
    <CompletenessPanel
      completeness={completeness}
      error={completenessError}
      onRetry={() => {
        setCompletenessError(null);
        loadCompleteness();
      }}
      onGenerate={generate}
      generating={generating}
      generateError={generateError}
    />
  );

  const chatSuggestions = completeness?.can_generate
    ? ["ทักษะไหนของฉันเด่นที่สุด", "เงินเดือนเริ่มต้นสายนักพัฒนาประมาณเท่าไร"]
    : ["ช่วยถามสิ่งที่ยังขาดให้หน่อย", "เงินเดือนเริ่มต้นสายนักพัฒนาประมาณเท่าไร"];

  return (
    <>
      {steps}
      <div className="mx-auto w-full max-w-[1120px] px-4 pt-8 pb-24 md:px-6 md:pt-10">
        <header>
          <h1 className="text-h1 font-bold text-text">เริ่มจากเรื่องราวของคุณ</h1>
          <p className="mt-1 text-body text-text-muted">อัปโหลด CV หรือทำแบบสอบถามอย่างน้อยหนึ่งอย่าง · เลือกทำแท็บใดก่อนก็ได้</p>
        </header>

        {/* Below lg: the sidebar collapses into a score bar above the content */}
        <div className="sticky top-16 z-30 mt-6 rounded-lg border border-border bg-bg/95 shadow-sm backdrop-blur lg:hidden">
          <button
            type="button"
            aria-expanded={sidebarOpen}
            aria-controls="completeness-mobile"
            onClick={() => setSidebarOpen((v) => !v)}
            className="flex min-h-12 w-full items-center gap-3 px-4 text-left"
          >
            <span className="text-small font-semibold text-text">ความครบถ้วน</span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-border" aria-hidden="true">
              <span className="block h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${completeness?.score ?? 0}%` }} />
            </span>
            <span className="tabular text-small font-semibold text-text">{completeness ? `${completeness.score}%` : "–"}</span>
            <ChevronDown className={`size-4 text-text-muted transition-transform duration-200 ${sidebarOpen ? "rotate-180" : ""}`} strokeWidth={2} aria-hidden="true" />
          </button>
          {!sidebarOpen && <ProfileChangesNote changes={completeness?.profile_changes} className="m-3 mt-0" />}
          {sidebarOpen && (
            <div id="completeness-mobile" className="max-h-[70vh] overflow-auto border-t border-border p-4">
              {panel}
            </div>
          )}
        </div>

        <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-6">
            <Tabs tab={tab} onChange={setTab} />
            <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
              {tab === "cv" && <CvTab onCompleteness={setCompleteness} onGoToQuestionnaire={() => setTab("questionnaire")} />}
              {tab === "questionnaire" && <QuestionnaireTab onCompleteness={setCompleteness} />}
              {tab === "chat" && (
                <ChatPanel
                  onCompleteness={setCompleteness}
                  suggestions={chatSuggestions}
                  subtitle="AI ถามต่อเฉพาะสิ่งที่ยังขาด · คำตอบจะถูกบันทึกเป็นหลักฐานในโปรไฟล์ · ใช้โควตาครั้งละ 1"
                />
              )}
            </div>
            <PrivacyCard />
          </div>

          <aside aria-label="ความครบถ้วนของข้อมูล" className="sticky top-24 hidden rounded-xl border border-border bg-glass p-6 shadow-sm lg:block">
            <h2 className="text-h3 font-semibold text-text">ความครบถ้วนของข้อมูล</h2>
            <p className="mt-0.5 mb-5 text-tiny text-text-muted">พร้อมสร้างเมื่อข้อมูลจำเป็นครบ และได้อย่างน้อย {THRESHOLD}%</p>
            {panel}
          </aside>
        </div>
      </div>
    </>
  );
}
