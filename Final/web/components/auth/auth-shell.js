import { ArrowRight, Compass, Eye, Puzzle } from "lucide-react";

// Register and Login layout (design/CareerMirror*/02-Register, 03-Login): page
// heading, a story card on the left and the form card on the right. On small
// screens the form comes first. Everything sits on the auth mesh gradient with
// frosted-glass cards (DesignSystem.md 1.3: glass only on gradient areas).

const POINTS = [
  { Icon: Eye, text: "เห็นจุดแข็งจากหลักฐานของคุณ" },
  { Icon: Puzzle, text: "เข้าใจช่องว่างที่ควรเติม" },
  { Icon: Compass, text: "เลือกสายงาน IT พร้อมก้าวถัดไป" },
];

// The mirror: skills you have now on the left, their next level reflected on the right.
const NOW = ["ภาษา Python", "SQL", "ทำงานเป็นทีม"];
const NEXT = ["REST API", "Docker", "สื่อสารกับลูกค้า"];

function Backdrop() {
  return (
    <div className="bg-auth-gradient absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div className="animate-drift absolute top-[18%] -left-[12%] size-[520px] rounded-full bg-[var(--auth-orb-1)] blur-3xl" />
      <div className="animate-drift-slow absolute -right-[10%] bottom-[-15%] size-[620px] rounded-full bg-[var(--auth-orb-2)] blur-3xl" />
      <div className="animate-drift absolute top-[-10%] right-[20%] size-[380px] rounded-full bg-[var(--auth-orb-3)] blur-3xl" />
    </div>
  );
}

function MirrorPanel() {
  return (
    <div className="relative overflow-hidden rounded-xl bg-primary-subtle/80 p-6 md:p-7 backdrop-blur-md">
      <p className="flex flex-wrap items-center gap-2 text-h3 font-bold text-text md:text-h2">
        คุณตอนนี้
        <ArrowRight className="size-5 text-accent" strokeWidth={2} aria-hidden="true" />
        คุณในก้าวถัดไป
      </p>
      <p className="mt-2 text-small text-text">
        ไม่ต้องมีประสบการณ์ทำงานก็เริ่มได้ เพียงเล่าทักษะและโปรเจกต์ของคุณ
      </p>

      {/* Decorative example, not user data */}
      <div className="mt-6 grid grid-cols-[1fr_auto_1fr] items-stretch gap-3" aria-hidden="true">
        <ul className="space-y-2">
          {NOW.map((s) => (
            <li key={s} className="rounded-full bg-bg px-3 py-1 text-center text-tiny font-medium text-text shadow-sm">
              {s}
            </li>
          ))}
        </ul>
        <span className="relative w-px bg-linear-to-b from-transparent via-accent to-transparent">
          <span className="absolute top-1/2 left-1/2 size-2 -translate-1/2 rounded-full bg-accent shadow-[0_0_12px_var(--color-accent)]" />
        </span>
        <ul className="space-y-2">
          {NEXT.map((s) => (
            <li
              key={s}
              className="rounded-full border border-dashed border-accent px-3 py-1 text-center text-tiny font-medium text-text"
            >
              {s}
            </li>
          ))}
        </ul>
      </div>
      <p className="mt-3 text-right text-tiny text-text-muted">ตัวอย่าง</p>
    </div>
  );
}

function StoryCard() {
  return (
    <section
      aria-labelledby="auth-story"
      className="glass-card animate-rise flex flex-col gap-6 rounded-xl p-6 [animation-delay:120ms] md:p-8"
    >
      <h2 id="auth-story" className="text-h3 font-semibold text-text">
        พื้นที่ที่ช่วยให้คุณมองเห็นตัวเอง
      </h2>
      <ul className="space-y-3">
        {POINTS.map(({ Icon, text }) => (
          <li key={text} className="flex items-center gap-3 text-body text-text">
            <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-md bg-bg/70 text-accent shadow-sm">
              <Icon className="size-[18px]" strokeWidth={1.75} aria-hidden="true" />
            </span>
            {text}
          </li>
        ))}
      </ul>
      <MirrorPanel />
    </section>
  );
}

/** Page frame for /register and /login. `children` is the form card body. */
export function AuthShell({ title, subtitle, cardTitle, children }) {
  return (
    <div className="relative isolate flex-1">
      <Backdrop />
      <div className="mx-auto w-full max-w-[1120px] px-4 pt-12 pb-20 md:px-6 md:pt-16">
        <header className="animate-rise">
          <h1 className="text-h1 font-bold text-text md:text-[36px] md:leading-[52px]">{title}</h1>
          <p className="mt-1 text-body text-text">{subtitle}</p>
        </header>

        <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1fr)] lg:gap-8">
          <section
            aria-labelledby="auth-form-title"
            className="glass-card animate-rise order-first rounded-xl p-6 [animation-delay:60ms] md:p-8 lg:order-last"
          >
            <h2 id="auth-form-title" className="text-h3 font-semibold text-text">
              {cardTitle}
            </h2>
            {children}
          </section>
          <StoryCard />
        </div>
      </div>
    </div>
  );
}
