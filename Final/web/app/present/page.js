import {
  ArrowRight,
  Ban,
  BookOpenText,
  Bot,
  Calculator,
  CheckCircle2,
  Coins,
  Cpu,
  EyeOff,
  FileText,
  Filter,
  Gauge,
  GitMerge,
  HelpCircle,
  Layers,
  ListChecks,
  MousePointerClick,
  Quote,
  RefreshCw,
  Route,
  Scale,
  Search,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
  TimerOff,
  TriangleAlert,
  UserCheck,
  UserRound,
  Workflow,
} from "lucide-react";
import { DotGrid } from "@/components/motion/dot-grid";
import { ShaderBackground } from "@/components/ui/shader-background";
import { Columns, GrowBar, UsageMeter } from "@/components/present/present-visuals";
import { PresentTimeline } from "@/components/present/present-timeline";
import { Explain, ExplainLayer } from "@/components/present/explain";
import { CHAPTERS } from "@/components/present/chapters";
import { ClaimCheckDemo, JevCostCalculator, RouterSimulator, RrfDemo } from "@/components/present/interactive";

// Presentation page /present: CareerMirror for the course presentation, 5 chapters that put
// LLM, RAG and Jev in the spotlight: problem, LLM, RAG, Jev (cost and Jev vs Groq), and results
// with next steps. The app itself is demonstrated live, not on this page. Figures come from
// docs/Design.md, docs/JevEvaluation.md, benchmarks/careermirror_v1, e2e/runs and the test runs.
// Not linked from anywhere and not indexed. Every number
// comes from docs/Design.md, e2e/runs and the test runs; numbers not measured yet
// are marked as pending.
// Copy rule: every Thai text is a full semi-formal sentence (subject, verb, object).
// Slides lead with visuals (icons, numbers, charts) and a one-line label; every longer
// sentence lives in the block's click-to-open card (`tip`, explain.js).
// Type is larger than the rest of the site (.present-type in globals.css), for reading
// while presenting.

export const metadata = {
  title: "การนำเสนอโปรเจกต์ CareerMirror",
  robots: { index: false, follow: false },
};

const BRAND_SILK = ["#0a1820", "#173d55", "#6fbfae", "#0f2230"];

/* ---------- shared pieces ---------- */

/** Chapter heading. The subtitle (`children`) is read in the click card, not on the slide. */
function SectionHeading({ no, eyebrow, title, tip, children }) {
  const detail = [children, tip].filter(Boolean);
  return (
    <Explain tip={detail.length ? detail : undefined} title={title} className="mx-auto max-w-4xl rounded-2xl p-2 text-center">
      <p className="text-tiny font-semibold tracking-[0.12em] text-accent uppercase">
        <span className="tabular mr-2 rounded-full bg-primary-subtle px-2 py-0.5 text-text">{no}</span>
        {eyebrow}
      </p>
      <h2 className="mt-3 text-h1 font-bold text-text md:text-[44px] md:leading-[62px]">{title}</h2>
    </Explain>
  );
}

/** A slide panel. `note` is a footnote read in the click card, after `tip`. */
function Tile({ icon: Icon, title, tip, note, className = "", children }) {
  const detail = [tip, note].filter(Boolean);
  return (
    <Explain tip={detail.length ? detail : undefined} title={title} className={`flex flex-col rounded-2xl border border-border bg-surface p-5 shadow-sm ${className}`}>
      {title && (
        <h3 className="mb-4 flex items-center gap-2 text-small font-semibold text-text">
          {Icon && <Icon className="size-5 shrink-0 text-accent" strokeWidth={1.75} aria-hidden="true" />}
          {title}
        </h3>
      )}
      {children}
    </Explain>
  );
}

function Big({ value, unit, caption }) {
  return (
    <div>
      <p className="tabular font-[family-name:var(--font-latin-first)] text-[48px] leading-none font-semibold tracking-tight text-text">
        {value}
        {unit && <span className="ml-1 text-h3 font-medium text-text-muted">{unit}</span>}
      </p>
      {caption && <p className="mt-2 text-tiny text-text-muted">{caption}</p>}
    </div>
  );
}

/** Points with a check mark: the title on the slide, the body and tip in its click card. */
function CheckList({ items, className = "space-y-2", Icon = CheckCircle2, tone = "text-success" }) {
  return (
    <ul className={className}>
      {items.map(({ t, b, tip }) => (
        <Explain as="li" key={t} tip={[b, tip].filter(Boolean)} title={t} className="flex items-center gap-3 rounded-xl border border-border bg-bg/60 backdrop-blur-md p-3 text-small">
          <Icon className={`size-6 shrink-0 ${tone}`} strokeWidth={1.75} aria-hidden="true" />
          <span className="font-semibold text-text">{t}</span>
        </Explain>
      ))}
    </ul>
  );
}

/** Steps in order, numbered, three to a row on wide screens; `strong` marks the step to look at. */
function FlowChain({ steps }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {steps.map(({ Icon, label, sub, tip, strong }, i) => (
        <Explain
          as="li"
          key={label}
          tip={[sub, tip].filter(Boolean)}
          title={label}
          className={`relative flex items-center gap-4 rounded-xl border p-4 ${strong ? "border-accent bg-primary-subtle" : "border-border bg-bg/60 backdrop-blur-md"}`}
        >
          <span className="tabular absolute top-2 right-3 text-tiny font-semibold text-text-muted">{i + 1}</span>
          <span className={`inline-flex size-12 shrink-0 items-center justify-center rounded-xl ${strong ? "bg-primary text-on-primary" : "bg-primary-subtle text-accent"}`}>
            <Icon className="size-6" strokeWidth={1.75} aria-hidden="true" />
          </span>
          <span className="min-w-0 pr-4 text-small font-semibold text-text">{label}</span>
        </Explain>
      ))}
    </ol>
  );
}

/* ---------- hero ---------- */

/** A soft dark glow behind centred text, so it stays readable over the bright silk folds. */
function TextGlow() {
  return <div className="absolute inset-0 -z-10 bg-[radial-gradient(55%_60%_at_50%_45%,rgb(12_25_34/0.7),transparent_75%)]" aria-hidden="true" />;
}

function Hero() {
  return (
    <section className="bg-brand-gradient relative isolate overflow-hidden">
      <ShaderBackground colors={BRAND_SILK} className="absolute inset-0 -z-10" />
      <div className="hero-scrim absolute inset-0 -z-10" aria-hidden="true" />
      <DotGrid vertical="top" className="-z-10" />
      <TextGlow />
      <div className="mx-auto max-w-[1120px] px-4 pt-20 pb-28 text-center md:px-6 md:pt-28 md:pb-36">
        <p className="text-small font-semibold text-hero-muted">Advanced Topics in Computer Software · RMUTT</p>
        <h1 className="mx-auto mt-4 max-w-4xl text-[38px] leading-[56px] font-bold text-hero-fg md:text-[58px] md:leading-[80px]">
          CareerMirror
          <br />
          ใช้ AI เฉพาะงานที่ต้องใช้ภาษาเท่านั้น
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-body text-hero-muted">
          LLM เขียนคำอธิบาย RAG ค้นความรู้ภาษาไทย และ Jev เลือกเส้นทางด้วยต้นทุนต่ำ ส่วน Python คำนวณตัวเลขและการตัดสินใจทั้งหมด
        </p>
        <ol className="mx-auto mt-10 flex max-w-4xl flex-wrap justify-center gap-2">
          {CHAPTERS.map((c, i) => (
            <li key={c}>
              <a
                href={`#s${i + 1}`}
                data-transition="off"
                className="inline-flex min-h-10 items-center gap-2 rounded-full border border-hero-muted/30 bg-white/5 px-4 text-small text-hero-fg backdrop-blur transition-colors duration-150 hover:bg-white/15"
              >
                <span className="tabular font-semibold text-hero-cta">{i + 1}</span>
                {c}
              </a>
            </li>
          ))}
        </ol>
        <p className="mt-8 inline-flex items-center gap-2 text-tiny text-hero-muted">
          <MousePointerClick className="size-5" strokeWidth={1.75} aria-hidden="true" />
          ผู้ชมสามารถคลิกที่กล่องใดก็ได้เพื่ออ่านคำอธิบายโดยละเอียด
        </p>
      </div>
    </section>
  );
}

/* ---------- 1. problem and goal ---------- */

const PROBLEMS = [
  {
    Icon: HelpCircle,
    title: "ผู้ใช้ไม่ทราบว่าทักษะของตนเหมาะกับสายงานใด",
    body: "สายงาน IT มีหลายตำแหน่ง และแต่ละตำแหน่งต้องการทักษะในระดับที่แตกต่างกัน",
    tip: "นักศึกษาและผู้เริ่มทำงานมักรู้จักชื่อตำแหน่งงาน แต่ไม่ทราบว่าแต่ละตำแหน่งต้องการทักษะใดและต้องการในระดับใด ระบบจึงเก็บทักษะของผู้ใช้พร้อมระดับ แล้วนำไปเทียบกับโปรไฟล์ของ 26 สายงาน IT เพื่อให้ผู้ใช้เห็นว่าตนใกล้กับสายงานใดมากที่สุดและยังขาดทักษะใดบ้าง",
  },
  {
    Icon: Bot,
    title: "ทีมไม่สามารถให้ LLM ให้คะแนนผู้ใช้โดยตรงได้",
    body: "LLM ให้คะแนนต่างกันเมื่อถูกถามซ้ำ และผู้ใช้ไม่สามารถตรวจสอบได้ว่าคะแนนมาจากที่ใด",
    tip: "LLM สร้างคำตอบด้วยการสุ่มตามความน่าจะเป็น คำถามเดียวกันจึงอาจได้คะแนนต่างกันในแต่ละครั้ง นอกจากนี้ LLM ไม่สามารถแสดงที่มาของคะแนนในรูปแบบที่ตรวจสอบได้ หากระบบใช้คะแนนจาก LLM ผู้ใช้จะไม่สามารถเชื่อถือผลลัพธ์หรือนำผลไปเปรียบเทียบข้ามช่วงเวลาได้",
  },
  {
    Icon: Target,
    title: "ทีมจึงกำหนดหลักการออกแบบไว้ 3 ข้อ",
    body: "ระบบต้องคำนวณคะแนนซ้ำได้ผลเดิม ระบบต้องอธิบายที่มาของคะแนนได้ และทุกข้อความต้องชี้กลับไปยังหลักฐานของผู้ใช้",
    tip: "หลักข้อแรกทำให้ข้อมูลชุดเดิมได้คะแนนเดิมทุกครั้ง หลักข้อที่สองทำให้ผู้ใช้เห็นว่าคะแนนแต่ละส่วนมาจากทักษะใด และหลักข้อที่สามทำให้ทุกประโยคที่ AI เขียนมีหมายเลขอ้างอิงไปยังบรรทัดใน CV คำตอบในแบบสอบถาม หรือข้อความในแชท หลักทั้ง 3 ข้อนี้กำหนดการออกแบบของทุกส่วนที่ปรากฏในบทถัดไป",
  },
];

const FLOW = [
  {
    Icon: FileText,
    title: "ผู้ใช้ป้อนข้อมูลได้ 3 ช่องทาง",
    body: "ผู้ใช้สามารถอัปโหลด CV ตอบแบบสอบถาม หรือพูดคุยผ่านแชทได้",
    tip: "ช่องทางทั้งสามเสริมกัน CV ให้ข้อมูลประสบการณ์และทักษะที่ผู้ใช้เขียนไว้ แบบสอบถามให้ระดับทักษะที่ผู้ใช้ประเมินเองและความชอบในการทำงาน ส่วนแชทจะถามคำถามเพิ่มเติมเฉพาะข้อมูลที่ยังขาด ระบบคำนวณความครบถ้วนของข้อมูล และอนุญาตให้สร้างโปรไฟล์เมื่อข้อมูลเพียงพอแล้ว",
  },
  {
    Icon: UserRound,
    title: "ระบบสร้างโปรไฟล์ที่มีหลักฐานกำกับ",
    body: "โปรไฟล์ระบุทักษะ ระดับทักษะ และความชอบในการทำงานของผู้ใช้",
    tip: "ข้อมูลทุกชิ้นในโปรไฟล์มี evidence id ที่ชี้กลับไปยังแหล่งที่มา ระบบเลือกระดับทักษะตามลำดับที่กำหนดไว้ คือกฎที่อ่านจาก CV ก่อน จากนั้นจึงเป็นระดับที่ผู้ใช้ประเมินในแบบสอบถาม และระดับล่าสุดที่ผู้ใช้บอกในแชท",
  },
  {
    Icon: Layers,
    title: "ระบบเทียบโปรไฟล์กับ 26 สายงาน IT",
    body: "Python คำนวณเปอร์เซ็นต์ความตรงของแต่ละสายงาน",
    tip: "ระบบเทียบทักษะของผู้ใช้กับทักษะที่แต่ละสายงานต้องมีและควรมี รวมถึงทักษะการทำงานและความชอบในการทำงาน แล้วรวมผลเป็นเปอร์เซ็นต์ด้วยสูตรถ่วงน้ำหนักที่ตายตัว น้ำหนักของสูตรคือ 70% ทักษะที่ต้องมี 15% ทักษะที่ควรมี 10% ทักษะการทำงาน และ 5% ความชอบในการทำงาน",
  },
  {
    Icon: Sparkles,
    title: "ระบบแนะนำก้าวถัดไปให้ผู้ใช้",
    body: "ผู้ใช้เห็นทักษะที่ยังขาด ช่วงเงินเดือน และสภาพตลาดงานในกรุงเทพฯ",
    tip: "Python คำนวณทักษะที่ยังขาดจากส่วนต่างระหว่างระดับของผู้ใช้กับระดับที่สายงานต้องการ AI เขียนคำแนะนำหนึ่งข้อต่อหนึ่งช่องว่าง โดยอ้างอิงเส้นทางการเรียนรู้จากคลังความรู้ ส่วนเงินเดือนและตลาดงานมาจากตารางอ้างอิงและแคชประกาศงาน ดังนั้น LLM จึงไม่ได้เขียนตัวเลขเหล่านี้เอง",
  },
];

function ProblemSection() {
  return (
    <section id="s1" className="mx-auto w-full max-w-[1120px] scroll-mt-20 px-4 py-20 md:px-6">
      <SectionHeading
        no="1"
        eyebrow="โปรเจกต์นี้แก้ปัญหาอะไร"
        title="ผู้ใช้ควรรู้จักตนเองก่อนเลือกสายงาน IT"
        tip="CareerMirror ช่วยให้ผู้ใช้เห็นภาพสะท้อนของตนเองจากหลักฐานที่ผู้ใช้ให้มา ทีมจำกัดขอบเขตไว้ที่สายงาน IT และตลาดงานในกรุงเทพฯ เพื่อให้ข้อมูลอ้างอิงมีความลึกและตรวจสอบได้ภายในเวลาพัฒนาที่มีอยู่"
      >
        โปรเจกต์นี้ครอบคลุมเฉพาะสายงาน IT ใช้ข้อมูลงานในกรุงเทพฯ และแสดงผลเป็นภาษาไทย
      </SectionHeading>
      <ul className="mt-12 grid gap-5 md:grid-cols-3">
        {PROBLEMS.map(({ Icon, title, body, tip }) => (
          <Explain as="li" key={title} tip={[body, tip]} title={title} className="flex flex-col items-center rounded-2xl border border-border bg-surface p-6 text-center shadow-sm">
            <span className="inline-flex size-20 items-center justify-center rounded-2xl bg-primary text-on-primary">
              <Icon className="size-10" strokeWidth={1.5} aria-hidden="true" />
            </span>
            <h3 className="mt-5 text-h3 font-semibold text-text">{title}</h3>
          </Explain>
        ))}
      </ul>
      <ol className="mt-8 grid gap-3 md:grid-cols-4">
        {FLOW.map(({ Icon, title, body, tip }, i) => (
          <Explain as="li" key={title} tip={[body, tip]} title={title} className="relative flex flex-col items-center gap-3 rounded-2xl border border-border bg-surface p-5 text-center shadow-sm">
            <span className="inline-flex size-14 shrink-0 items-center justify-center rounded-full bg-primary-subtle text-primary">
              <Icon className="size-7" strokeWidth={1.5} aria-hidden="true" />
            </span>
            <span className="text-small font-semibold text-text">{title}</span>
            {i < FLOW.length - 1 && (
              <ArrowRight className="absolute top-1/2 -right-3 z-10 hidden size-5 -translate-y-1/2 rounded-full bg-bg text-accent md:block" strokeWidth={2} aria-hidden="true" />
            )}
          </Explain>
        ))}
      </ol>
    </section>
  );
}

/* ---------- 2. LLM ---------- */

const PATH = [
  {
    Icon: UserRound,
    label: "web",
    sub: "Next.js แสดงหน้าเว็บภาษาไทย",
    tip: "หน้าเว็บสร้างด้วย Next.js และเรียก API ผ่าน proxy ฝั่ง server ดังนั้น cookie ที่ใช้ยืนยันตัวตนจึงอยู่เฉพาะฝั่ง server หน้าเว็บไม่ได้ติดต่อกับ LLM โดยตรงในทุกกรณี",
  },
  {
    Icon: Server,
    label: "API",
    sub: "FastAPI รับคำขอและตรวจสิทธิ์",
    tip: "API เป็นจุดเดียวที่ตรวจสิทธิ์ ตรวจรูปแบบข้อมูล และตรวจโควตาก่อนเรียก LLM ทุกครั้ง การรวมการควบคุมไว้ที่ API ทำให้ทีมจัดการทั้งความปลอดภัยและต้นทุนได้จากจุดเดียว",
  },
  {
    Icon: Route,
    label: "AI Router",
    sub: "Router เลือกเส้นทางให้ข้อความ",
    tip: "Router อ่านข้อความของผู้ใช้แล้วตัดสินว่าข้อความนั้นถามเรื่องใด เช่น ทักษะ เงินเดือน หรือการแก้โปรไฟล์ Router ใช้กฎที่ไม่ต้องเรียก LLM ก่อน และเรียกโมเดลเฉพาะเมื่อกฎตัดสินไม่ได้ เมื่อทีมเปิดใช้ Jev ระบบจะถาม Jev ก่อน และถาม Groq เมื่อ Jev ไม่แน่ใจ ผู้ชมสามารถดูรายละเอียดได้ในบทที่ 4",
  },
  {
    Icon: Search,
    label: "RAG · ข้อมูลภายนอก · คะแนน Python",
    sub: "ระบบเตรียมข้อเท็จจริงก่อนส่งให้ LLM",
    tip: "ก่อนเรียก LLM ระบบรวบรวมข้อเท็จจริงที่เส้นทางนั้นต้องใช้ ได้แก่ ความรู้จากคลังเอกสารผ่าน RAG ข้อมูลเงินเดือนและตลาดงาน และคะแนนที่ Python คำนวณไว้แล้ว LLM จึงไม่ต้องคิดตัวเลขหรือข้อเท็จจริงขึ้นเอง",
  },
  {
    Icon: Bot,
    label: "LLM",
    sub: "LLM เรียบเรียงข้อความ",
    strong: true,
    tip: "LLM ได้รับเฉพาะข้อเท็จจริงที่ระบบเตรียมไว้ และมีหน้าที่เรียบเรียงข้อความภาษาไทยให้ผู้ใช้อ่านเข้าใจง่าย LLM ต้องตอบเป็น JSON ที่มีโครงสร้าง และทุกข้อความต้องอ้าง evidence id",
  },
  {
    Icon: ShieldCheck,
    label: "ระบบตรวจหลักฐาน",
    sub: "parse_claims ตรวจทุกข้อความ",
    tip: "parse_claims ตรวจว่า evidence id ที่ LLM อ้างมีอยู่จริง และตรวจว่าตัวเลขในประโยคตรงกับข้อเท็จจริง ระบบตัดประโยคที่ไม่ผ่านออก และหากไม่เหลือประโยคใดผ่าน ระบบจะแสดงข้อความที่คำนวณจากข้อมูลแทน",
  },
];

const MODELS = [
  {
    id: "openai/gpt-oss-120b",
    role: "ข้อความที่ผู้ใช้อ่าน",
    body: "โมเดลนี้เขียนข้อความที่ผู้ใช้อ่าน ได้แก่ โปรไฟล์ เหตุผลการจับคู่ และก้าวถัดไป",
    tip: "โมเดลขนาดใหญ่เขียนภาษาไทยได้เป็นธรรมชาติกว่า ทีมจึงใช้โมเดลนี้กับข้อความที่ผู้ใช้อ่านโดยตรง ซึ่งเป็นส่วนที่คุณภาพของภาษามีผลต่อความเชื่อถือมากที่สุด",
    strong: true,
  },
  {
    id: "qwen/qwen3.8-27b",
    role: "งานเชิงโครงสร้างและโมเดลสำรอง",
    body: "โมเดลนี้ทำงานเชิงโครงสร้าง ได้แก่ Router การแก้โปรไฟล์ และการดึงข้อเท็จจริง และยังทำหน้าที่เป็นโมเดลสำรองด้วย",
    tip: "งานเชิงโครงสร้างต้องการคำตอบสั้นในรูป JSON มากกว่าภาษาที่สวยงาม โมเดลที่เล็กกว่าจึงตอบได้เร็วกว่าและใช้ tokens น้อยกว่า เมื่อโมเดลหลักเรียกไม่สำเร็จ ระบบจะสลับมาใช้โมเดลนี้แทน",
  },
  {
    id: "jev-latest · TypeSafe",
    role: "เลือกเส้นทางใน Router",
    body: "Jev เลือกเส้นทางของข้อความใน Router เป็นด่านแรกเมื่อทีมเปิดใช้งาน และ Groq ตรวจซ้ำเมื่อ Jev ไม่แน่ใจ",
    tip: "Jev ไม่ได้ทำงานผ่าน Groq แต่เรียก API ของ TypeSafe โดยตรง ระบบใช้ Jev กับงานเดียว คือการเลือกเส้นทางของข้อความ เพื่อลดจำนวนครั้งที่ต้องเรียก Groq ผู้ชมสามารถดูรายละเอียดได้ในบทที่ 4",
  },
];

const LIMITS = [
  { value: "30", unit: "คำขอ / นาที", caption: "Groq รับคำขอได้ไม่เกินจำนวนนี้ต่อนาที", tip: "ข้อจำกัดนี้ทำให้ระบบต้องลดจำนวนครั้งที่เรียก LLM ต่อหนึ่งการกระทำของผู้ใช้ Router จึงใช้กฎก่อนเรียก LLM" },
  { value: "1,000", unit: "คำขอ / วัน", caption: "Groq รับคำขอได้ไม่เกินจำนวนนี้ต่อวัน", tip: "เมื่อทีมแบ่งจำนวนนี้ให้ผู้ใช้คนละ 40 คำขอต่อวัน ระบบจะรองรับผู้ใช้ที่ใช้งานเต็มโควตาได้ประมาณ 25 คนต่อวัน" },
  { value: "8,000", unit: "tokens / นาที", caption: "Groq รับ tokens ได้ไม่เกินจำนวนนี้ต่อนาที", tip: "ข้อจำกัดนี้เข้มงวดที่สุด เพราะการสร้างโปรไฟล์หนึ่งครั้งอาจใช้หลายพัน tokens ทีมจึงจำกัด prompt ไม่ให้เกิน 5,000 tokens และเลือกไม่ใช้ agent ที่วนเรียก LLM หลายรอบ" },
  { value: "200,000", unit: "tokens / วัน", caption: "Groq รับ tokens ได้ไม่เกินจำนวนนี้ต่อวัน", tip: "ทีมตั้งโควตาผู้ใช้ไว้ที่ 40,000 tokens ต่อวัน เพื่อไม่ให้ผู้ใช้เพียงไม่กี่คนใช้ปริมาณรวมของทั้งวันจนหมด" },
];

const CLAIM_STEPS = [
  {
    Icon: ListChecks,
    title: "ระบบเตรียม facts พร้อม evidence id",
    body: "แต่ละ fact ชี้ไปยังบรรทัดใน CV ข้อในแบบสอบถาม หรือข้อความในแชท",
    tip: "ระบบสร้างรายการข้อเท็จจริงจากข้อมูลที่ผู้ใช้ยืนยันแล้ว และกำหนด id ให้แต่ละข้อ id นี้เป็นสิ่งเดียวที่ LLM ใช้อ้างอิงได้ LLM จึงไม่สามารถอ้างแหล่งที่ไม่มีอยู่จริงได้โดยไม่ถูกจับ",
  },
  {
    Icon: Bot,
    title: "LLM เขียนข้อความ",
    body: "LLM ตอบเป็น JSON และแต่ละข้อความอ้าง id ของหลักฐาน",
    tip: "รูปแบบ JSON ทำให้ระบบแยกข้อความแต่ละข้อและ id ที่อ้างได้อย่างแน่นอน ระบบไม่ต้องตีความข้อความอิสระของ LLM",
  },
  {
    Icon: Filter,
    title: "parse_claims ตรวจข้อความ",
    body: "ฟังก์ชันนี้ตัด id ที่ไม่มีอยู่จริง และตัดตัวเลขที่ไม่อยู่ใน facts",
    tip: "parse_claims ตรวจทุกประโยคก่อนบันทึก ประโยคที่อ้าง id ผิดหรือมีตัวเลขที่ไม่ตรงกับข้อเท็จจริงจะถูกตัดทิ้ง ฟังก์ชันนี้ยังตัด id ที่หลุดมาในเนื้อความ เพื่อให้ผู้ใช้เห็นหลักฐานในรูปหมายเลขอ้างอิงเท่านั้น",
  },
  {
    Icon: Quote,
    title: "ผู้ใช้เห็นหมายเลขอ้างอิง [n]",
    body: "ผู้ใช้กดดูที่มาของทุกข้อความได้",
    tip: "หน้าโปรไฟล์และแชทแสดงหมายเลขอ้างอิงท้ายข้อความ เมื่อผู้ใช้วางเมาส์หรือกดที่หมายเลข ระบบจะแสดงชื่อแหล่งที่มาและข้อความต้นฉบับ ผู้ใช้จึงตรวจได้ทันทีว่าข้อความมาจากข้อมูลส่วนใดของตน",
  },
];

const GUARD_LAYERS = [
  {
    Icon: Ban,
    title: "ขาเข้า: Guard ตรวจข้อความก่อนส่งถึง LLM",
    chips: ["ว่าง / ยาวเกิน", "prompt injection", "ขอดู system prompt", "นอกขอบเขต"],
    items: [
      "Guard ปฏิเสธข้อความว่างหรือข้อความที่ยาวเกิน 1,000 ตัวอักษร",
      "Guard จับ prompt injection ทั้งภาษาไทยและภาษาอังกฤษ เช่น “ignore previous instructions” และ “ไม่ต้องสนใจคำสั่ง”",
      "Guard ปฏิเสธคำขอดู system prompt แต่ผู้ใช้ยังถามถึงทักษะ “system prompt” ได้",
      "Guard ปฏิเสธเรื่องนอกขอบเขต เช่น หวย ดูดวง และ MBTI",
    ],
    note: "ระบบปฏิเสธทันทีโดยไม่ใช้ LLM และไม่ใช้โควตาของผู้ใช้",
    tip: "Guard เป็นโค้ดที่ตรวจด้วยรูปแบบข้อความ จึงทำงานเร็วและไม่มีต้นทุน Guard แยกความต่างระหว่างการขอดู system prompt ซึ่งเป็นการโจมตี กับการถามถึงทักษะการเขียน system prompt ซึ่งเป็นคำถามปกติของสายงาน AI",
  },
  {
    Icon: Filter,
    title: "ขาออก: ระบบตรวจทุกข้อความก่อนแสดง",
    chips: ["evidence id", "ตัวเลข", "ชื่อเครื่องมือ / บริษัท"],
    items: [
      "parse_claims ตัดข้อความที่อ้าง evidence id ที่ไม่มีอยู่จริง",
      "ตัวเลขในข้อความต้องตรงกับค่าที่คำนวณ และหากไม่ตรง ระบบจะใช้ template แทน",
      "ระบบตัดข้อความที่อ้างชื่อเครื่องมือ บริษัท หรือใบรับรองที่ไม่อยู่ใน facts",
    ],
    note: "ระบบยังตรวจชื่อที่เขียนเป็นภาษาไทยด้วยวิธีนี้ไม่ได้",
    tip: "การตรวจขาออกป้องกันกรณีที่ LLM แต่งข้อมูลขึ้นเอง แม้ prompt จะสั่งไว้ชัดเจนแล้วก็ตาม การตรวจชื่อเฉพาะทำงานกับชื่อที่เขียนด้วยอักษรละติน เพราะระบบเทียบกับค่าใน facts ได้ตรงตัว ส่วนชื่อภาษาไทยยังเป็นข้อจำกัดที่ทีมยอมรับไว้",
  },
  {
    Icon: UserCheck,
    title: "การกระทำ: LLM เสนอ และผู้ใช้เป็นผู้ตัดสิน",
    chips: ["allow-list", "ตรวจค่า", "กดยืนยัน", "15 นาที"],
    items: ["LLM ไม่สามารถเขียนข้อมูลลงโปรไฟล์ได้เอง", "การแก้ไขต้องอยู่ใน allow-list และต้องผ่านการตรวจค่า", "ระบบบันทึกเมื่อผู้ใช้กดปุ่มยืนยันเท่านั้น"],
    note: "ข้อเสนอแต่ละรายการจะหมดอายุภายใน 15 นาที",
    tip: "ชั้นนี้จำกัดสิ่งที่ LLM ทำได้ แม้ผู้โจมตีจะหลอก LLM สำเร็จ LLM ก็ทำได้เพียงเสนอการแก้ไขที่ผู้ใช้มองเห็นและต้องกดยืนยันเอง ความเสียหายจึงจำกัดอยู่ในขอบเขตที่ผู้ใช้ควบคุมได้",
  },
];

/** Numbered steps in a row; steps with `llm` are highlighted as the only LLM calls. */
function StepRow({ steps, cols = "md:grid-cols-3 lg:grid-cols-6" }) {
  return (
    <ol className={`grid gap-2 ${cols}`}>
      {steps.map(({ Icon, title, body, tip, llm }, i) => (
        <Explain
          as="li"
          key={title}
          tip={[body, tip].filter(Boolean)}
          title={`ขั้นที่ ${i + 1}: ${title}`}
          className={`relative flex flex-col items-center rounded-xl p-4 text-center ${llm ? "bg-[var(--color-series-1)] text-white" : "border border-border bg-bg/60 backdrop-blur-md text-text"}`}
        >
          <span className={`tabular absolute top-2 right-3 text-tiny font-semibold ${llm ? "text-white/80" : "text-text-muted"}`}>{i + 1}</span>
          <Icon className={`size-9 ${llm ? "text-white" : "text-accent"}`} strokeWidth={1.5} aria-hidden="true" />
          <p className="mt-2 text-small font-semibold">{title}</p>
        </Explain>
      ))}
    </ol>
  );
}

const PROFILE_STEPS = [
  {
    Icon: ListChecks,
    title: "ระบบตรวจความพร้อม",
    body: "ระบบตรวจ can_generate และโควตาของผู้ใช้",
    tip: "can_generate ตรวจว่าผู้ใช้ยืนยัน CV หรือตอบแบบสอบถามแล้ว และมีข้อมูลเพียงพอสำหรับการสร้างโปรไฟล์ ระบบตรวจโควตาในขั้นนี้ด้วย เพื่อไม่ให้ระบบเรียก LLM เมื่อผู้ใช้ใช้โควตาหมดแล้ว",
  },
  {
    Icon: FileText,
    title: "ระบบสร้าง facts",
    body: "ทุก fact มี evidence id ที่ชี้ไปยังบรรทัดใน CV คำตอบ หรือข้อความในแชท",
    tip: "ขั้นนี้รวบรวมข้อมูลจากทั้ง 3 ช่องทางเป็นรายการเดียว และกำหนด id ให้แต่ละรายการ id เหล่านี้กลายเป็นหมายเลขอ้างอิงที่ผู้ใช้เห็นบนโปรไฟล์",
  },
  {
    Icon: EyeOff,
    title: "ระบบตัดข้อมูลส่วนตัว",
    body: "ระบบไม่ส่งอีเมล ลิงก์ และเบอร์โทรศัพท์ให้ LLM",
    tip: "ข้อมูลเหล่านี้ไม่จำเป็นต่อการสรุปประสบการณ์ ระบบจึงตัดออกก่อนส่งออกไปยังผู้ให้บริการ LLM ภายนอก เพื่อลดความเสี่ยงที่ข้อมูลส่วนตัวของผู้ใช้จะรั่วไหล",
  },
  {
    Icon: Bot,
    title: "LLM เขียนสรุป",
    body: "LLM เขียนสรุปประสบการณ์และสิ่งที่ควรสำรวจในรูปแบบ JSON",
    tip: "ขั้นนี้เป็นขั้นเดียวใน workflow ที่เรียก LLM ระบบจำกัด prompt ไม่ให้เกิน 5,000 tokens และสั่งให้ LLM เขียนจากข้อเท็จจริงที่ได้รับเท่านั้น",
    llm: true,
  },
  {
    Icon: Filter,
    title: "parse_claims ตรวจข้อความ",
    body: "ฟังก์ชันนี้ตัดข้อความที่ไม่มีหลักฐาน หรือมีตัวเลขที่ไม่อยู่ใน facts",
    tip: "นอกจากการตรวจ id และตัวเลข ขั้นนี้ยังตัดข้อความสรุปประสบการณ์ที่อ้างทักษะซึ่งไม่อยู่ใน facts และตัดทักษะที่ผู้ใช้เคยลบออกไปแล้ว",
  },
  {
    Icon: Calculator,
    title: "ระบบบันทึกและจับคู่",
    body: "Python คำนวณความตรงกับ 26 สายงาน",
    tip: "ระบบบันทึกโปรไฟล์พร้อมหลักฐาน แล้วคำนวณเปอร์เซ็นต์ความตรงกับทุกสายงานด้วยสูตรถ่วงน้ำหนักที่ตายตัว (70% ทักษะที่ต้องมี 15% ทักษะที่ควรมี 10% ทักษะการทำงาน และ 5% ความชอบในการทำงาน) ขั้นนี้ไม่ใช้ LLM และให้ผลเดิมทุกครั้งเมื่อข้อมูลไม่เปลี่ยน",
  },
];

function LlmSection() {
  return (
    <section id="s2" className="bg-section-wash scroll-mt-20 py-20">
      <div className="mx-auto w-full max-w-[1120px] px-4 md:px-6">
        <SectionHeading
          no="2"
          eyebrow="LLM"
          title="LLM เขียนคำอธิบายจากข้อเท็จจริงที่ระบบเตรียมไว้ และโค้ดตรวจทุกคำตอบ"
          tip="ทีมวาง LLM ไว้ที่ขั้นท้าย ๆ ของเส้นทาง เพราะ LLM ควรรับข้อมูลที่ผ่านการคัดกรองและคำนวณแล้วเท่านั้น LLM จึงมีหน้าที่เดียว คือเรียบเรียงภาษา ส่วนคะแนน ระดับ และเงินเดือนมาจาก Python ทั้งหมด"
        >
          ส่วนประกอบของ AI ทั้งหมดอยู่ใน API และตัวเลขทุกตัวที่ผู้ใช้เห็นมาจาก Python ข้อมูลชุดเดิมจึงได้ผลลัพธ์เดิมทุกครั้ง
        </SectionHeading>

        <Tile
          icon={Workflow}
          title="คำขอหนึ่งรายการเดินทางผ่าน 6 ขั้นตอน และ LLM เป็นเพียงหนึ่งขั้น"
          tip="กล่องนี้แสดงลำดับที่ข้อความของผู้ใช้เดินทางผ่านระบบ ตั้งแต่หน้าเว็บจนถึงการตรวจหลักฐาน ทุกขั้นก่อน LLM มีหน้าที่เตรียมข้อมูลให้ LLM และขั้นหลัง LLM มีหน้าที่ตรวจคำตอบ"
          className="mt-12 p-6"
        >
          <FlowChain steps={PATH} />
        </Tile>

        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <Tile
            icon={Cpu}
            title="2 โมเดลของ Groq แบ่งงานตามลักษณะงาน"
            tip="งานที่ผู้ใช้อ่านโดยตรงใช้โมเดลที่ใหญ่กว่า ส่วนงานที่ตอบเป็นโครงสร้างใช้โมเดลที่เล็กและเร็วกว่า การแบ่งงานแบบนี้ช่วยประหยัด tokens ภายใต้ข้อจำกัดของ Groq และ Jev ช่วยรับงานเลือกเส้นทางไปจาก Groq อีกส่วนหนึ่ง"
            note="ทีมเก็บ model id ไว้ใน env จึงเปลี่ยนโมเดลได้โดยไม่ต้องแก้โค้ด"
          >
            <div className="space-y-2">
              {MODELS.map((m) => (
                <Explain key={m.id} tip={[m.body, m.tip]} title={m.id} className={`rounded-xl border p-3 ${m.strong ? "border-accent/50 bg-primary-subtle/50 backdrop-blur-md" : "border-border bg-bg/60 backdrop-blur-md"}`}>
                  <code className="text-small font-semibold text-text">{m.id}</code>
                  <span className="mt-1.5 block w-fit rounded-full bg-primary-subtle px-2.5 py-0.5 text-tiny font-semibold text-accent">{m.role}</span>
                </Explain>
              ))}
            </div>
          </Tile>
          <Tile
            icon={Gauge}
            title="Groq จำกัดทั้งบัญชี และนี่คือเหตุผลที่ทีมนำ Jev มาใช้"
            tip="Groq กำหนดเพดานการใช้งานแยกตามโมเดล และทุก API key ในบัญชีเดียวกันใช้เพดานร่วมกัน ข้อจำกัดเหล่านี้ทำให้ทีมใช้กฎก่อนเรียก LLM ตั้งโควตาต่อผู้ใช้ และย้ายงานเลือกเส้นทางไปให้ Jev ในบทที่ 4"
            note="นอกจากนี้ ระบบยังจำกัดผู้ใช้แต่ละคนไว้ที่ 40 คำขอและ 40,000 tokens ต่อวัน และตรวจโควตาก่อนเรียก LLM ทุกครั้ง"
          >
            <div className="grid grid-cols-2 gap-2">
              {LIMITS.map((l) => (
                <Explain key={l.caption} tip={[l.caption, l.tip]} title={`${l.value} ${l.unit}`} className="rounded-xl border border-border bg-bg/60 backdrop-blur-md px-3 py-3">
                  <p className="tabular text-h2 font-semibold text-text">{l.value}</p>
                  <p className="text-tiny text-text-muted">{l.unit}</p>
                </Explain>
              ))}
            </div>
          </Tile>

          <Tile
            icon={ShieldCheck}
            title="โค้ดตรวจทุกข้อความก่อนแสดง LLM จึงแต่งข้อมูลขึ้นเองไม่ได้"
            note="ทีมยังไม่ได้วัดสัดส่วนประโยคที่ parse_claims ตัดทิ้งในการสร้างโปรไฟล์จริง"
            tip="ปัญหาที่พบบ่อยของ LLM คือการแต่งข้อมูลที่ฟังดูน่าเชื่อ (hallucination) ระบบนี้บังคับให้ทุกข้อความอ้างหลักฐาน แล้วใช้โค้ดตรวจการอ้างอิงนั้น แทนการเชื่อคำตอบของ LLM โดยตรง"
            className="lg:col-span-2"
          >
            <ol className="grid gap-3 md:grid-cols-4">
              {CLAIM_STEPS.map(({ Icon, title, body, tip }, i) => (
                <Explain as="li" key={title} tip={[body, tip]} title={title} className="relative flex flex-col items-center rounded-xl border border-border bg-bg/60 backdrop-blur-md p-4 text-center">
                  <span className="tabular absolute top-2 right-3 text-tiny font-semibold text-text-muted">{i + 1}</span>
                  <Icon className="size-9 text-accent" strokeWidth={1.5} aria-hidden="true" />
                  <p className="mt-2 text-small font-semibold text-text">{title}</p>
                </Explain>
              ))}
            </ol>
            <div className="mt-4">
              <ClaimCheckDemo />
            </div>
          </Tile>

          <Tile
            icon={ShieldAlert}
            title="Guardrail ครอบ LLM ไว้ทั้งขาเข้า ขาออก และการกระทำ"
            tip="ทีมไม่พึ่งให้ LLM ปฏิเสธคำขอที่ไม่เหมาะสมเอง เพราะ LLM อาจถูกหลอกด้วย prompt injection ได้ ทีมจึงวาง guardrail เป็นโค้ดไว้ 3 จุด คือก่อนถึง LLM หลัง LLM ตอบ และที่ขอบเขตสิทธิ์ของ LLM"
            className="lg:col-span-2"
          >
            <ol className="grid gap-3 lg:grid-cols-3">
              {GUARD_LAYERS.map(({ Icon, title, chips, items, note, tip }) => (
                <Explain as="li" key={title} tip={[...items, note, tip]} title={title} className="flex flex-col items-center rounded-xl border border-border bg-bg/60 backdrop-blur-md p-4 text-center">
                  <Icon className="size-9 text-accent" strokeWidth={1.5} aria-hidden="true" />
                  <p className="mt-2 text-small font-semibold text-text">{title}</p>
                  <ul className="mt-2 flex flex-wrap justify-center gap-1.5">
                    {chips.map((c) => (
                      <li key={c} className="rounded-full border border-border bg-surface px-2.5 py-0.5 text-tiny font-semibold text-text-muted">
                        {c}
                      </li>
                    ))}
                  </ul>
                </Explain>
              ))}
            </ol>
          </Tile>

          <Tile
            icon={Workflow}
            title="Workflow สร้างโปรไฟล์มี 6 ขั้น และเรียก LLM เพียง 1 ขั้น"
            note="หากไม่มีข้อความสรุปประสบการณ์ข้อใดผ่านการตรวจ ระบบจะแสดงรายการประสบการณ์ตามที่บันทึกไว้แทน"
            tip="โค้ดกำหนดลำดับขั้นไว้ล่วงหน้า ทีมไม่ใช้ agent ที่ให้ LLM เลือกเครื่องมือและวนทำงานเอง เพราะต้องการต้นทุนที่คาดการณ์ได้และทดสอบได้ทีละขั้น กล่องสีเข้มคือขั้นเดียวที่เรียก LLM"
            className="lg:col-span-2"
          >
            <StepRow steps={PROFILE_STEPS} />
          </Tile>
        </div>
      </div>
    </section>
  );
}

/* ---------- 3. RAG ---------- */

const RAG_PARTS = [
  {
    name: "BM25",
    body: "BM25 ตัดคำภาษาไทยด้วย pythainlp และจับชื่อทักษะที่ตรงตัว",
    tip: "BM25 ให้คะแนนเอกสารตามคำที่ตรงกับคำค้น จึงเหมาะกับชื่อเฉพาะ เช่น Kubernetes หรือ SQL ที่การค้นด้วยเวกเตอร์อาจจับได้ไม่แม่น ภาษาไทยไม่มีการเว้นวรรคระหว่างคำ ระบบจึงใช้ pythainlp ตัดคำก่อนสร้างดัชนี",
  },
  {
    name: "FAISS vector",
    body: "FAISS ค้นด้วย multilingual-e5-base และจับความหมายของคำถาม",
    tip: "โมเดล embedding แปลงคำถามและเอกสารเป็นเวกเตอร์ แล้ว FAISS ค้นเอกสารที่มีความหมายใกล้เคียงกัน วิธีนี้จับคำถามที่ใช้ถ้อยคำต่างจากเอกสารได้ ทีมเลือก e5-base เพราะโมเดลนี้มีขนาดประมาณครึ่งหนึ่งของ bge-m3 และทำงานบน CPU ได้เร็วพอ",
  },
];

// From api/app/rag/chunking.py; the character counts are measured on the current /data files.
const CHUNK_FACTS = [
  {
    k: "Chunk size",
    v: "ตามหัวข้อ",
    tip: "ระบบไม่ได้กำหนดขนาด chunk ตายตัว แต่ตัดตามหัวข้อระดับ ## ขนาดจริงจึงอยู่ระหว่าง 259 ถึง 1,065 ตัวอักษร ค่ากลางคือ 441 ตัวอักษร รวมชื่อเอกสารและชื่อหัวข้อที่ระบบใส่ไว้ต้น chunk แล้ว ทีมยังไม่ได้ทดลองเทียบกับการตัดแบบกำหนดขนาดตายตัว",
  },
  {
    k: "Overlap",
    v: "ไม่มี",
    tip: "แต่ละหัวข้อเป็น 1 chunk เนื้อหาจึงไม่ซ้อนกัน ระบบใส่ชื่อเอกสารและชื่อหัวข้อไว้ต้น chunk แทน ทำให้แต่ละ chunk อ่านเข้าใจได้ในตัว",
  },
  {
    k: "จำนวน chunk",
    v: "80",
    tip: "ไฟล์สายงาน 26 ไฟล์ แบ่งเป็นคำอธิบายสายงาน 26 chunk และเส้นทางการเรียนรู้ 26 chunk พร้อม soft skill 21 chunk และ work style 7 chunk",
  },
];

// Where RAG feeds the LLM in the app.
const RAG_USES = [
  {
    name: "ระบบเขียนเหตุผลการจับคู่และก้าวถัดไป",
    kind: "rag",
    how: "ระบบดึงเส้นทางการเรียนรู้จาก RAG และ LLM เขียนคำแนะนำหนึ่งข้อต่อหนึ่งช่องว่างที่คำนวณไว้แล้ว",
    tip: "Python คำนวณว่าผู้ใช้ขาดทักษะใดในแต่ละสายงาน จากนั้น RAG ค้นเอกสารเส้นทางการเรียนรู้ของสายงานนั้น LLM จึงเขียนคำแนะนำโดยอิงทั้งช่องว่างที่คำนวณไว้และเอกสารที่ค้นได้ ส่วนเปอร์เซ็นต์และรายการทักษะที่ต้องเติมยังคงมาจาก Python",
  },
  {
    name: "ระบบตอบคำถามเรื่องทักษะและจุดบอด",
    kind: "rag",
    how: "parse_claims ตรวจคำตอบ และหากคำตอบไม่ผ่าน ระบบจะใช้ข้อความที่คำนวณไว้แทน",
    tip: "เมื่อผู้ใช้ถามว่าตนเก่งด้านใดหรือมีจุดบอดตรงไหน ระบบส่งทักษะ ระดับ และบันทึกเรื่อง soft skill จาก RAG ให้ LLM เรียบเรียงคำตอบ คำตอบในแชทยังผ่านการตรวจเพิ่มเติม เช่น ระบบตัดประโยคที่อ้างชื่อเครื่องมือหรือบริษัทที่ไม่มีในข้อเท็จจริง",
  },
];

// Golden Dataset careermirror_v2, 134 retrieval cases searched without a filter, run 6 Nov 2026 on
// develop fc82b1d (CareerMirror-Test-Results/2026-11-06_golden-v2-benchmark).
const GOLDEN_RAG = [
  { label: "Hybrid Hit@3", value: 130, strong: true, mark: 107, tip: "การค้นแบบ hybrid ที่ระบบใช้จริงพบเอกสารที่ถูกต้องใน 3 อันดับแรก 130 จาก 134 คำถาม เส้นประคือเกณฑ์ Hit@3 0.8 หรือราว 107 จาก 134 คำถาม ข้อที่พลาด 3 ใน 4 ข้อเป็นหมวดใหม่ที่ให้อนุมาน soft skill จากพฤติกรรม" },
  { label: "BM25 Hit@3", value: 121, mark: 107, tip: "BM25 เพียงอย่างเดียวพบเอกสารที่ถูกต้องใน 3 อันดับแรก 121 จาก 134 คำถาม หมวดที่อ่อนที่สุดคือเส้นทางการเรียนรู้ ซึ่งได้ 19 จาก 26 คำถาม" },
  { label: "Hybrid Hit@1", value: 108, strong: true, tip: "การค้นแบบ hybrid จัดเอกสารที่ถูกต้องไว้อันดับแรก 108 จาก 134 คำถาม ระบบจึงส่งเอกสารหลายชิ้นให้ LLM แทนการส่งเพียงชิ้นเดียว การค้นด้วยเวกเตอร์อย่างเดียวได้ 110 แต่ Hit@3 ได้เพียง 124" },
  { label: "BM25 Hit@1", value: 94, tip: "BM25 เพียงอย่างเดียวจัดเอกสารที่ถูกต้องไว้อันดับแรก 94 จาก 134 คำถาม" },
];

function RagSection() {
  const ragUses = RAG_USES.map((f) => ({ t: f.name, b: f.how, tip: f.tip }));
  return (
    <section id="s3" className="scroll-mt-20 py-20">
      <div className="mx-auto w-full max-w-[1120px] px-4 md:px-6">
        <SectionHeading
          no="3"
          eyebrow="RAG"
          title="Hybrid RAG ค้นความรู้ภาษาไทยได้ถูก 130 จาก 134 คำถามใน 3 อันดับแรก"
          tip="RAG ค้นความรู้จากคลังเอกสารที่ทีมเขียนเองก่อน แล้วจึงให้ LLM เขียนคำตอบโดยอ้างอิงเอกสารที่ค้นได้ ทีมรวมการค้นสองวิธี เพราะแต่ละวิธีมีจุดอ่อนต่างกัน"
        >
          ทีมวัดด้วย Golden Dataset ภาษาไทย 134 คำถาม ซึ่งครอบคลุมคำอธิบายสายงาน เส้นทางการเรียนรู้ soft skill และ work style รวมถึงคำถามที่ต้องนำความรู้ไปใช้กับสถานการณ์จริง ผลแยกตามวิธีค้นอยู่ในบทที่ 5
        </SectionHeading>

        <div className="mt-12 grid gap-5 lg:grid-cols-2">
          <Tile
            icon={Search}
            title="ระบบค้นด้วยสองวิธีพร้อมกัน แล้วรวมอันดับด้วย RRF"
            tip="BM25 พลาดเมื่อผู้ใช้ใช้คำต่างจากเอกสาร ส่วนการค้นด้วยเวกเตอร์พลาดกับชื่อเฉพาะ การรวมสองวิธีจึงให้ผลดีกว่าการใช้วิธีเดียว ระบบค้นภายใน API โดยไม่ต้องเพิ่ม vector database"
          >
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
              <div className="space-y-2">
                {RAG_PARTS.map((p) => (
                  <Explain key={p.name} tip={[p.body, p.tip]} title={p.name} className="flex items-center gap-3 rounded-xl border border-border bg-bg/60 backdrop-blur-md p-3">
                    <Search className="size-6 shrink-0 text-accent" strokeWidth={1.75} aria-hidden="true" />
                    <p className="text-small font-semibold text-text">{p.name}</p>
                  </Explain>
                ))}
              </div>
              <ArrowRight className="size-5 text-accent" strokeWidth={2} aria-hidden="true" />
              <Explain
                tip="RRF รวมอันดับจากทั้งสองวิธี และกรองตามสายงานและหมวด Reciprocal Rank Fusion ให้คะแนนเอกสารแต่ละชิ้นเท่ากับ 1/(k + อันดับ) จากแต่ละวิธี แล้วนำคะแนนมารวมกัน ค่า k = 60 ลดความได้เปรียบของอันดับแรกสุด เอกสารที่ทั้งสองวิธีจัดอันดับสูงจึงขึ้นมาอยู่อันดับต้น"
                title="RRF k = 60"
                className="rounded-xl border border-accent bg-primary-subtle/60 backdrop-blur-md p-3 text-center"
              >
                <GitMerge className="mx-auto size-7 text-accent" strokeWidth={1.75} aria-hidden="true" />
                <p className="mt-1 text-small font-semibold text-text">RRF k = 60</p>
              </Explain>
            </div>
            <Explain
              tip="ทีมเขียนคลังความรู้เอง ประกอบด้วยไฟล์สายงาน 26 ไฟล์ และบันทึกเรื่อง work style และ soft skill ระบบตัด chunk ตามหัวข้อระดับ ## ทำให้แต่ละ chunk มีเนื้อหาครบในตัว และแต่ละ chunk เก็บ doc_id หมวด สายงาน และแหล่งที่มาไว้ การอ้างอิงในคำตอบจึงชี้ไปยังเนื้อหาที่มีอยู่จริงในคลัง"
              title="คลังความรู้ที่ทีมเขียนเอง"
              className="mt-4 flex items-center gap-3 rounded-xl border border-border bg-bg/60 backdrop-blur-md p-3"
            >
              <BookOpenText className="size-8 shrink-0 text-accent" strokeWidth={1.5} aria-hidden="true" />
              <span className="tabular text-h2 font-semibold text-text">26</span>
              <span className="text-small font-semibold text-text">ไฟล์สายงาน + บันทึก work style และ soft skill</span>
            </Explain>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              {CHUNK_FACTS.map(({ k, v, tip }) => (
                <Explain key={k} tip={tip} title={k} className="rounded-xl border border-border bg-bg/60 backdrop-blur-md px-2 py-2">
                  <p className="text-tiny text-text-muted">{k}</p>
                  <p className="tabular text-small font-semibold text-text">{v}</p>
                </Explain>
              ))}
            </div>
          </Tile>

          <Tile
            icon={Bot}
            title="RAG ช่วย LLM ตอบใน 2 งาน"
            tip="RAG ส่งเอกสารที่เกี่ยวข้องให้ LLM อ้างอิง LLM จึงไม่ต้องคิดคำแนะนำขึ้นเอง ส่วนเปอร์เซ็นต์และทักษะที่ต้องเติมยังคงมาจาก Python"
          >
            <CheckList items={ragUses} />
          </Tile>

          <Tile
            icon={GitMerge}
            title="ลองสลับวิธีจัดอันดับ แล้วดูว่า RRF ดึงเอกสารที่ถูกขึ้นมาอย่างไร"
            tip="BM25 ให้คำอธิบายสายงานอยู่อันดับแรกเพราะคำตรงกัน ส่วน Vector ให้เส้นทางการเรียนรู้อยู่อันดับแรกเพราะความหมายตรงกัน RRF รวมสองอันดับ เอกสารที่ทั้งสองวิธีจัดไว้สูงจึงได้คะแนนรวมมากที่สุด"
            className="lg:col-span-2"
          >
            <RrfDemo />
          </Tile>
        </div>
      </div>
    </section>
  );
}

/* ---------- 4. Jev ---------- */

const JEV_TRIED = [
  {
    t: "Jev อย่างเดียวแทน Groq",
    b: "Jev ได้ 55/62 ส่วน Groq ได้ 61/62 บนข้อความที่มีเฉลยชัดเจน",
    tip: "Jev มักถามกลับเมื่อไม่แน่ใจ ซึ่งทำให้ผู้ใช้ต้องพิมพ์ใหม่ ทีมจึงให้ Groq ตัดสินต่อเมื่อ Jev จะถามกลับ",
  },
  {
    t: "แทน Keyword rules",
    b: "กฎได้ 82/87 ส่วน Jev ตามด้วย Groq ได้ 80/87",
    tip: "ทีมทดลองแบบเงา โดยผู้ใช้ไม่ได้รับผลจาก Jev Jev ชนะกฎ 3 ข้อแต่แพ้ 5 ข้อ และทั้ง 5 ข้อเป็นคำสั่งแก้โปรไฟล์ จึงไม่ผ่านเกณฑ์ที่ตั้งไว้ก่อนรัน",
  },
  {
    t: "ตรวจ claim ภาษาไทยด้วย Noul",
    b: "ตัด claim ที่ไม่มีหลักฐานได้ 4/18 และเก็บ claim ที่มีหลักฐานได้ 69/78",
    tip: "ทีมทดสอบกับ claim จริงจาก Groq 103 ข้อ ผลต่ำเกินกว่าจะใช้ตัด claim ก่อนแสดงให้ผู้ใช้ และที่มาของเฉลยชุดนี้ยังรอการยืนยัน",
  },
  {
    t: "เลือกเอกสารจาก 3 อันดับแรก",
    b: "เมื่อกรองหมวดแบบระบบจริง ผลเท่าเดิม 22/22",
    tip: "เมื่อค้นทุกหมวดแบบ Golden Jev เพิ่ม Hit@1 จาก 58/74 เป็น 73/74 แต่ระบบจริงกรองหมวดและบทบาทก่อนค้น จึงไม่มีช่องให้ดีขึ้น การรันหยุดที่เพดาน token หลังเรียก 96 จาก 108 ครั้ง",
  },
];

// docs/JevEvaluation.md and Design.md §4.7. Groq figures are the Golden Dataset runs before Jev.
const JEV_COST = [
  { value: "$0.03", label: "ต่อการเลือกเส้นทาง 1,000 ครั้ง", tip: "การเรียก Jev หนึ่งครั้งใช้ input ประมาณ 650 tokens และ Jev คิดค่าบริการ $0.042 ต่อล้าน input tokens 1,000 ครั้งจึงมีค่าใช้จ่ายประมาณ $0.03 หรือราว 1 บาท" },
  { value: "$0", label: "ค่า output", tip: "Jev ไม่คิดค่า output และ Jev ตอบเพียงชื่อเส้นทางกับค่าความมั่นใจ ค่าใช้จ่ายทั้งหมดจึงมาจาก input" },
  { value: "$0.02", label: "ค่าทดสอบ Jev ทั้งหมด", tip: "ทีมใช้เงินประมาณ $0.02 สำหรับการทดลองทุกจุดใน JevEvaluation.md รวมการทดลองที่ไม่ได้นำมาใช้" },
  { value: "0", label: "tokens ที่หักจากโควตาผู้ใช้", tip: "tokens ของ Jev ไม่นับรวมในโควตา tokens ต่อวันของผู้ใช้ ซึ่งออกแบบมาเพื่อติดตามข้อจำกัดของ Groq ข้อความยังนับเป็น 1 คำขอตามปกติ" },
];

const JEV_VS_GROQ = [
  { k: "เรียก Groq เพื่อเลือกเส้นทาง", groq: "9 ครั้ง", jev: "3 ครั้ง", win: "jev", tip: "บน Golden Dataset มี 3 เคสที่ถึงชั้น LLM รวม 9 ครั้งใน 3 รอบ เมื่อใช้ Jev Jev ตัดสินเองได้ 2 เคส จึงเหลือเคสเดียวที่ต้องถาม Groq" },
  { k: "tokens ของ Groq ในชั้นนี้", groq: "3,150", jev: "1,038", win: "jev", tip: "tokens ที่ไม่ต้องใช้ใน Router กลายเป็นงบประมาณของงานที่ผู้ใช้อ่านโดยตรง เช่น การสร้างโปรไฟล์และเหตุผลการจับคู่ ซึ่ง Groq จำกัดไว้ที่ 8,000 tokens ต่อนาทีทั้งบัญชี" },
  { k: "ค่าใช้จ่ายของชั้นนี้", groq: "โควตา Groq ของบัญชี", jev: "≈ $0.03 / 1,000 ครั้ง", win: "jev", tip: "Groq ในโปรเจกต์นี้ถูกจำกัดด้วยเพดานต่อนาทีและต่อวันของทั้งบัญชี การย้ายงานเลือกเส้นทางไปให้ Jev จึงคืนโควตาที่หายากที่สุดให้งานอื่น โดยมีค่าใช้จ่ายเพียงราว 1 บาทต่อ 1,000 ครั้ง" },
  { k: "เลือกเส้นทางถูก (Golden)", groq: "60/60", jev: "60/60", tip: "ทั้งสองเวอร์ชันได้คะแนนเต็ม ชุดนี้จึงแยกความแม่นยำของสองเวอร์ชันไม่ได้" },
  { k: "ชุดใหม่ 43 ข้อ", groq: "43/43", jev: "43/43", tip: "ทีมเขียนชุดนี้และล็อกเกณฑ์ก่อนรัน ระบบที่ใช้ Jev คู่กับ Groq ตอบถูกทุกข้อเท่ากับ Groq อย่างเดียว และ Jev ตัดสินเองได้ 33 ข้อ" },
  { k: "เวลาเฉลี่ยในชั้น LLM", groq: "257 ms", jev: "476 ms", win: "groq", tip: "ชั้นนี้ช้าลงเพราะข้อความที่ Jev ตอบ clarify ต้องเรียกทั้ง Jev และ Groq ข้อความที่กฎตัดสินได้ไม่ได้รับผลกระทบ และเวลาทั้งคำขอส่วนใหญ่เป็นเวลาที่ Groq เขียนคำตอบ" },
];

function JevSection() {
  return (
    <section id="s4" className="bg-section-wash scroll-mt-20 py-20">
      <div className="mx-auto w-full max-w-[1120px] px-4 md:px-6">
        <SectionHeading
          no="4"
          eyebrow="Jev · เทคนิคใหม่ของโปรเจกต์"
          title="Jev ลดการเรียก Groq ลง 2 ใน 3 ด้วยต้นทุนราว $0.03 ต่อ 1,000 ครั้ง"
          tip="Jev คือโมเดลของ TypeSafe (jev-latest) ที่ตอบคำถามแบบเลือกตอบ (Choice) ทีมใช้ Jev ในจุดเดียว คือชั้น LLM ของ AI Router บน Golden Dataset ความแม่นยำเท่าเดิม และการเรียก Groq ลดจากเดิมราว 2 ใน 3 แลกกับชั้น LLM ที่ช้าลง ทีมยังไม่พบว่า Jev ทำให้ระบบแม่นขึ้น"
        >
          Jev เลือกเส้นทางของข้อความแทน Groq ส่วน Groq ยังเขียนคำตอบภาษาไทยทุกข้อความ
        </SectionHeading>

        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {JEV_COST.map(({ value, label, tip }, i) => (
            <Explain
              key={label}
              tip={tip}
              title={`${value} ${label}`}
              className={`flex flex-col items-center rounded-2xl border p-5 text-center shadow-sm ${i === 0 ? "border-[var(--color-series-1)] bg-[var(--color-series-1)] text-white" : "border-border bg-surface text-text"}`}
            >
              <Coins className={`size-7 ${i === 0 ? "text-white" : "text-accent"}`} strokeWidth={1.5} aria-hidden="true" />
              <p className="tabular mt-2 font-[family-name:var(--font-latin-first)] text-[44px] leading-none font-semibold tracking-tight">{value}</p>
              <p className={`mt-2 text-small font-semibold ${i === 0 ? "text-white/90" : "text-text-muted"}`}>{label}</p>
            </Explain>
          ))}
        </div>

        <Tile
          icon={Coins}
          title="ลองเลื่อนดู: ค่าใช้จ่ายของ Jev และภาระของ Groq ต่อวัน"
          tip="Groq จำกัดโมเดล Router ไว้ที่ 1,000 คำขอต่อวัน และทุก API key ในบัญชีใช้เพดานร่วมกัน เมื่อ Jev ตัดสินแทน Groq ได้ราว 2 ใน 3 ระบบจึงรับข้อความได้มากขึ้นก่อนชนเพดาน ในขณะที่ค่า Jev ยังเป็นเพียงเศษเซนต์ต่อวัน"
          className="mt-5"
        >
          <JevCostCalculator />
        </Tile>

        <Tile
          icon={Scale}
          title="Jev เทียบกับ Groq ในชั้นเลือกเส้นทาง"
          tip="ทีมรัน Golden Dataset บนระบบสองชุดแยกกัน คือก่อนใส่ Jev และเมื่อใช้ Jev คู่กับ Groq แถวสีเขียวคือด้านที่ดีกว่า แถวสีส้มคือสิ่งที่ทีมยอมแลก"
          className="mt-5"
        >
          <div className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)] gap-x-3 px-3 pb-2 text-tiny font-semibold text-text-muted">
            <span>ตัววัด</span>
            <span className="text-center">Groq อย่างเดียว</span>
            <span className="text-center text-accent">Jev → Groq</span>
          </div>
          <ul className="space-y-2">
            {JEV_VS_GROQ.map(({ k, groq, jev, win, tip }) => (
              <Explain
                as="li"
                key={k}
                tip={tip}
                title={k}
                className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)] items-center gap-x-3 rounded-xl border border-border bg-bg/60 backdrop-blur-md p-3"
              >
                <span className="text-small text-text">{k}</span>
                <span className={`tabular text-center text-small font-semibold ${win === "groq" ? "text-success" : "text-text-muted"}`}>{groq}</span>
                <span className={`tabular text-center text-small font-semibold ${win === "jev" ? "text-success" : win === "groq" ? "text-warning" : "text-text-muted"}`}>{jev}</span>
              </Explain>
            ))}
          </ul>
        </Tile>

        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <Tile
            icon={Route}
            title="ลองส่งข้อความผ่าน AI Router แล้วดูว่าใครตัดสิน"
            tip="Router มี 4 ชั้น Guard และ Keyword rules ตัดสินข้อความส่วนใหญ่โดยไม่เรียกโมเดล ข้อความที่เหลือถึงชั้น LLM ซึ่ง Jev ตัดสินก่อน และ Groq รับช่วงต่อเมื่อ Jev ไม่แน่ใจหรือเรียกไม่สำเร็จ ลำดับนี้มาจากฟังก์ชัน decide และ ask_router_model ในโค้ดของ API"
            note="ทีมปิด Jev ไว้เป็นค่าเริ่มต้น ระบบเปิดใช้ Jev เมื่อตั้ง JEV_ROUTER_ENABLED=true และใส่ TYPESAFE_API_KEY เท่านั้น Jev ได้รับเฉพาะข้อความและบทสนทนาล่าสุด"
            className="lg:col-span-2"
          >
            <RouterSimulator />
          </Tile>

          <Tile
            icon={Ban}
            title="จุดอื่นที่ทีมทดลอง Jev แต่ไม่นำมาใช้"
            tip="ทีมใช้ผลการทดลองตัดสินว่าจะใช้ Jev ที่จุดใด จุดเหล่านี้ไม่ผ่านเกณฑ์หรือไม่มีช่องให้ดีขึ้น ระบบจึงใช้ Jev เฉพาะการเลือกเส้นทางในชั้น LLM"
            className="lg:col-span-2"
          >
            <CheckList items={JEV_TRIED} className="grid gap-2 sm:grid-cols-2" Icon={Ban} tone="text-warning" />
          </Tile>
        </div>
      </div>
    </section>
  );
}

/* ---------- 5. results and next steps ---------- */

const ROUTER_LAYER_SCORES = [
  { k: "Guard", v: "9/9", tip: "ข้อความ 3 เคส รันเคสละ 3 รอบ จบที่ Guard และเลือกเส้นทางถูกทุกครั้ง" },
  { k: "Rules", v: "42/42", tip: "ข้อความ 14 เคส รันเคสละ 3 รอบ จบที่ Keyword rules และเลือกเส้นทางถูกทุกครั้ง" },
  { k: "LLM", v: "9/9", tip: "ข้อความ 3 เคส รันเคสละ 3 รอบ ถึงชั้น LLM Jev เลือกเส้นทางก่อน และ Groq ตัดสินเฉพาะเคสที่ Jev ตอบ clarify" },
];

const RELIABILITY = [
  { Icon: RefreshCw, title: "ระบบลองใหม่ 1 ครั้ง", body: "ระบบลองใหม่เมื่อพบ 429, error หรือปัญหาเครือข่าย", tip: "ข้อผิดพลาดส่วนใหญ่ของ Groq เกิดขึ้นชั่วคราว เช่น การเกินเพดานต่อนาที การลองใหม่เพียงครั้งเดียวจึงกู้คืนได้เกือบทุกกรณีโดยไม่ทำให้ผู้ใช้รอนานเกินไป" },
  { Icon: GitMerge, title: "ระบบสลับไปใช้โมเดลสำรอง", body: "โมเดลสำรองคือ qwen3.8-27b", tip: "Groq นับเพดานแยกตามโมเดล เมื่อโมเดลหลักเกินเพดาน โมเดลสำรองจึงมักยังมีโควตาเหลืออยู่" },
  { Icon: TriangleAlert, title: "ระบบแจ้งผู้ใช้เป็นภาษาไทย", body: "ระบบแจ้งข้อผิดพลาดและคืนโควตาให้ผู้ใช้", tip: "เมื่อทั้งสองโมเดลล้ม ระบบจะแจ้งผู้ใช้ด้วยข้อความที่เข้าใจง่าย และคืนโควตาที่หักไป ผู้ใช้จึงไม่เสียโควตาจากความผิดพลาดที่ไม่ได้เกิดจากตนเอง" },
];

const EVAL_LIMITS = [
  "ชุดทดสอบยังมีขนาดเล็กและทีมเขียนขึ้นเอง ดังนั้นตัวเลขจริงอาจต่ำกว่านี้",
  "ทีมแยกชุดที่ใช้ปรับระบบ (47 ข้อ) ออกจากชุดที่ใช้วัดผล",
  "ทีมยังไม่ได้ทดสอบระบบกับผู้ใช้จริง",
  "ทีมยังไม่ได้ประเมินคุณภาพคำอธิบายของ LLM ด้วยคนหรือด้วย LLM-as-judge",
  "ผู้ทดสอบเขียนเฉลยของ Golden Dataset เอง และชุดนี้ยังรอผู้ตรวจอิสระ (draft_pending_human_review)",
  "Jev ทำให้ชั้น LLM ของ Router ช้าลงจาก 257 ms เป็น 476 ms และส่งข้อความแชทไปยังผู้ให้บริการอีกราย",
];

const NEXT_STEPS = [
  { t: "ทดสอบกับผู้ใช้จริง", tip: "ทีมยังไม่ได้ทดสอบระบบกับผู้ใช้จริง และยังไม่มีข้อความจากผู้ใช้จริงผ่าน Jev ตัวเลขทั้งหมดในบทที่ 5 จึงมาจากชุดทดสอบที่ทีมเขียนเอง" },
  { t: "ให้ผู้ตรวจอิสระรีวิว Golden Dataset", tip: "ผู้ทดสอบเขียนเฉลยเอง และ Golden Dataset ยังมีสถานะ draft_pending_human_review เกณฑ์คำตอบ 297 ข้อก็ยังไม่ได้ให้คะแนน คุณภาพของคำตอบจึงยังไม่ได้วัด" },
  { t: "วัดสัดส่วนประโยคที่ parse_claims ตัด", tip: "ค่านี้บอกว่า LLM แต่งข้อมูลบ่อยเพียงใดในการสร้างโปรไฟล์จริง ทีมยังไม่ได้วัด" },
  { t: "วัด p50 และ p95 ของเวลาตอบ", tip: "ทีมวัดเวลาตอบเป็นรายครั้ง แต่ยังไม่ได้วัดการกระจาย ทีมตั้งเป้าไว้ไม่เกิน 15 วินาที" },
  { t: "ตรวจชื่อภาษาไทยในคำตอบ", tip: "การตรวจชื่อเครื่องมือ บริษัท และใบรับรองขาออกทำงานกับชื่อที่เขียนด้วยอักษรละตินเท่านั้น" },
  { t: "แก้ปัญหาบทสนทนาค้างหัวข้อเดิม", tip: "บทสนทนาล่าสุดอาจทำให้ทั้ง Jev และ Groq เลือกเส้นทางของหัวข้อก่อนหน้า ปัญหานี้ยังเปิดอยู่" },
];

function ResultsSection() {
  return (
    <section id="s5" className="scroll-mt-20 py-20">
      <div className="mx-auto w-full max-w-[1120px] px-4 md:px-6">
        <SectionHeading
          no="5"
          eyebrow="ผลการวัดและสิ่งที่จะทำต่อ"
          title="ทีมวัดผลด้วยชุดข้อมูลภาษาไทย และระบบทำงานต่อได้เมื่อ LLM ล้ม"
          tip="ตัวเลขของ Router ในบทนี้มาจากการรันล่าสุดบนระบบที่ใช้ Jev คู่กับ Groq ชุดทดสอบเป็นชุดที่ทีมเขียนเอง จึงแสดงว่าระบบทำงานได้ตามที่ออกแบบ แต่ยังไม่ได้พิสูจน์ผลกับผู้ใช้จริง"
        />

        <div className="mt-12 grid gap-5 lg:grid-cols-2">
          <div className="grid content-start gap-5">
            <Tile
              icon={Route}
              title="Golden Dataset 100 เคส: AI Router เลือกเส้นทางถูกครบ"
              note="ทีมวัด Golden Dataset เมื่อวันที่ 5 พ.ย. บนระบบที่ใช้ Jev คู่กับ Groq และแก้ Keyword rules แล้ว ชุดนี้ได้ 60/60 ทั้งก่อนและหลังใส่ Jev จึงไม่ได้แสดงว่าระบบแม่นขึ้น"
              tip="Golden Dataset มี 100 เคส เป็นการค้นเอกสาร 80 เคส และบทสนทนา 20 เคส การเลือกเส้นทางวัดจาก 20 เคสนี้ รันเคสละ 3 รอบ ผ่าน API จริง ส่วนชุด 43 ข้อเป็นชุดแยกต่างหาก วัดเฉพาะข้อความที่ถึงชั้น LLM ก่อนการแก้ Keyword rules ทีมเขียนทั้งสองชุดเอง และยังไม่ผ่านผู้ตรวจอิสระ"
            >
              <div className="grid grid-cols-2 gap-4">
                <Big value="60/60" caption="เคสบทสนทนา 20 จาก 100 เคส รัน 3 รอบ" />
                <Big value="43/43" caption="ข้อความที่ถึงชั้น LLM ชุดใหม่" />
              </div>
              <div className="mt-5 grid grid-cols-3 gap-2 text-center">
                {ROUTER_LAYER_SCORES.map(({ k, v, tip }) => (
                  <Explain key={k} tip={tip} title={k} className="rounded-xl border border-border bg-bg/60 backdrop-blur-md px-2 py-2">
                    <p className="text-tiny text-text-muted">{k}</p>
                    <p className="tabular text-small font-semibold text-text">{v}</p>
                  </Explain>
                ))}
              </div>
              <p className="mt-4 text-tiny text-text-muted">Golden ได้ 60/60 ทั้งก่อนและหลังใส่ Jev ตัวเลขนี้จึงยืนยันว่าความแม่นยำไม่ลดลง แต่ไม่ได้แสดงว่าแม่นขึ้น</p>
            </Tile>

            <Tile
              icon={Target}
              title="Golden Dataset 134 คำถาม: hybrid ดีกว่า BM25 ทั้ง Hit@1 และ Hit@3"
              tip="Hit@3 คือจำนวนคำถามที่เอกสารถูกต้องอยู่ใน 3 อันดับแรก ส่วน Hit@1 คือจำนวนที่อยู่อันดับแรกพอดี ชุดนี้ค้นทุกหมวดโดยไม่กรอง ซึ่งยากกว่าการใช้งานจริงที่ระบบกรองหมวดและสายงานก่อนค้น"
              note="ทีมรันทั้ง BM25 และ hybrid ด้วยโค้ดค้นของระบบเมื่อวันที่ 6 พ.ย. บน Golden Dataset v2 ซึ่งรวม 80 คำถามเดิม (hybrid ได้ 79/80 เท่าเดิม) และคำถามใหม่ 54 ข้อ ชุดนี้ยังรอผู้ตรวจอิสระ"
            >
              <ul className="space-y-3">
                {GOLDEN_RAG.map((b, i) => (
                  <GrowBar key={b.label} label={b.label} value={b.value} max={134} text={`${b.value}/134`} strong={b.strong} mark={b.mark} delay={i * 90} tip={b.tip} />
                ))}
              </ul>
            </Tile>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <Tile
              icon={CheckCircle2}
              title="ชุดทดสอบ End-to-end ของ API"
              note="การทดสอบกลุ่ม A–F ผ่านทั้งหมดในการรันวันที่ 4 พ.ย."
              tip="การทดสอบ end-to-end เรียก API จริงและแบ่งเป็น 6 กลุ่ม ได้แก่ การยืนยันตัวตน การอ่าน CV แบบสอบถาม โปรไฟล์และสายงาน แชทและการแก้ไข และโควตากับหน้า Admin"
            >
              <Big value="78/78" caption="กลุ่ม A–F ผ่าน" />
            </Tile>
            <Tile
              icon={ListChecks}
              title="Unit test และ integration test"
              note="pytest ผ่านครบ 1,171 รายการบนโค้ดล่าสุดของ develop (9ae1e1b) รวมเทสต์ของ Jev และ Router"
              tip="unit test ตรวจฟังก์ชันแต่ละตัว เช่น สูตรคะแนน parse_claims และการเลือกเส้นทางของ Jev ส่วน integration test ตรวจการทำงานร่วมกันของ API กับฐานข้อมูล"
            >
              <Big value="1,171" caption="pytest ผ่าน" />
            </Tile>
            <Tile
              icon={TimerOff}
              title="ระบบทำ 3 ขั้นเมื่อเรียก LLM ไม่สำเร็จ"
              note="งาน Router มี timeout 7 วินาทีต่อครั้ง และระบบลองใหม่ทันที โดยทีมตั้งเป้าเวลารวมไว้ไม่เกิน 15 วินาที"
              tip="ลำดับนี้เรียงจากวิธีที่ผู้ใช้แทบไม่รู้สึกถึงปัญหา ไปจนถึงการแจ้งผู้ใช้โดยตรง ระบบจึงแจ้งข้อผิดพลาดเฉพาะเมื่อทุกทางสำรองใช้ไม่ได้แล้ว"
              className="sm:col-span-2"
            >
              <ol className="space-y-2">
                {RELIABILITY.map(({ Icon, title, body, tip }, i) => (
                  <Explain as="li" key={title} tip={[body, tip]} title={title} className="flex items-center gap-2 rounded-xl border border-border bg-bg/60 backdrop-blur-md p-3">
                    <span className="tabular inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-tiny font-semibold text-on-primary">{i + 1}</span>
                    <Icon className="size-5 shrink-0 text-accent" strokeWidth={1.5} aria-hidden="true" />
                    <span className="text-small font-semibold text-text">{title}</span>
                  </Explain>
                ))}
              </ol>
            </Tile>
          </div>
        </div>

        <Explain
          tip={[...EVAL_LIMITS, "ทีมระบุข้อจำกัดเหล่านี้ไว้อย่างเปิดเผย ตัวเลขในการนำเสนอนี้แสดงว่าระบบทำงานได้ตามที่ออกแบบ แต่ยังไม่ได้พิสูจน์ว่าผู้ใช้จริงจะได้รับประโยชน์ในระดับใด"]}
          title="การวัดผลครั้งนี้ยังมีข้อจำกัด"
          className="mt-5 rounded-2xl border border-info/40 bg-surface p-5 shadow-sm"
        >
          <h3 className="flex items-center gap-2 text-small font-semibold text-text">
            <TriangleAlert className="size-5 text-info" strokeWidth={2} aria-hidden="true" />
            การวัดผลครั้งนี้ยังมีข้อจำกัด
          </h3>
          <ul className="mt-3 flex flex-wrap gap-2">
            {["ชุดทดสอบเล็กและทีมเขียนเอง", "ยังไม่ทดสอบกับผู้ใช้จริง", "ยังไม่ประเมินคุณภาพคำอธิบาย", "Golden รอผู้ตรวจอิสระ", "ชั้น LLM ช้าลงเมื่อใช้ Jev"].map((l) => (
              <li key={l} className="rounded-full border border-info/40 bg-bg/60 backdrop-blur-md px-3 py-1 text-small font-semibold text-text">
                {l}
              </li>
            ))}
          </ul>
        </Explain>

        <Tile
          icon={ArrowRight}
          title="สิ่งที่ทีมจะทำต่อ"
          tip="รายการนี้มาจากข้อจำกัดที่ทีมระบุไว้ใน Design.md และ JevEvaluation.md ทุกข้อเป็นสิ่งที่ยังไม่ได้วัดหรือยังไม่ได้แก้"
          className="mt-5"
        >
          <CheckList items={NEXT_STEPS} className="grid gap-2 md:grid-cols-2 lg:grid-cols-3" Icon={ArrowRight} tone="text-accent" />
        </Tile>
      </div>
    </section>
  );
}

/* ---------- closing ---------- */

function Closing() {
  return (
    <section className="bg-brand-gradient relative isolate overflow-hidden">
      <ShaderBackground colors={BRAND_SILK} className="absolute inset-0 -z-10" />
      <div className="hero-scrim absolute inset-0 -z-10" aria-hidden="true" />
      <DotGrid vertical="top" className="-z-10" />
      <TextGlow />
      <div className="mx-auto max-w-[1120px] px-4 py-20 text-center md:px-6">
        <Sparkles className="mx-auto size-8 text-hero-muted" strokeWidth={1.5} aria-hidden="true" />
        <h2 className="mx-auto mt-4 max-w-3xl text-h1 font-bold text-hero-fg md:text-[44px] md:leading-[62px]">LLM เขียน RAG ค้นความรู้ และ Jev ลดภาระของ Groq</h2>
        <p className="mx-auto mt-3 max-w-2xl text-body text-hero-muted">
          Python คำนวณคะแนนและตัวเลขทั้งหมด ทุกข้อความมีหลักฐานกำกับ และ Jev ลดการเรียก Groq ลง 2 ใน 3 ด้วยต้นทุนราว $0.03 ต่อ 1,000 ครั้ง
        </p>
      </div>
    </section>
  );
}

export default function PresentPage() {
  return (
    <>
      {/* Outside .present-type: the side timeline keeps the site's normal type size. */}
      <PresentTimeline />
      <div className="present-type">
        <ExplainLayer />
        <Hero />
        <ProblemSection />
        <LlmSection />
        <RagSection />
        <JevSection />
        <ResultsSection />
        <Closing />
      </div>
    </>
  );
}
