import Image from "next/image";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Eye, GraduationCap, Presentation, ShieldCheck } from "lucide-react";
import {
  CvPreview,
  EvidencePreview,
  GapPreview,
  MatchCard,
  ProfileCard,
  RolesPreview,
  Thumb,
} from "@/components/landing/visuals";
import { WorkStyleAvatar } from "@/components/avatar/work-style-avatar";
import { DotGrid } from "@/components/motion/dot-grid";
import { ShaderBackground } from "@/components/ui/shader-background";
import { FinalAction, HeroActions } from "@/components/landing/landing-actions";
import { RolesShowcase } from "@/components/landing/roles-showcase";
import { StepsTimeline } from "@/components/landing/steps-timeline";
import ROLE_FILES from "@/lib/mock/fixtures/roles.json";

// Landing page (DesignSystem.md section 4): what the app does, how it works in
// 4 steps, privacy summary, สมัครใช้งาน / เข้าสู่ระบบ. Brand gradient and glass
// surfaces are used only on the hero, the card thumbnails and the cover bands.

// Silk shader colours from the brand (CIBrand.md section 3): deep navy folds with a
// teal-to-mint highlight, so text on top keeps its contrast with the scrim.
const BRAND_SILK = ["#0a1820", "#173d55", "#6fbfae", "#0f2230"];

const FEATURES = [
  {
    title: "อ่านทักษะจาก CV",
    body: "อัปโหลดไฟล์ PDF แล้วตรวจและแก้สิ่งที่ระบบอ่านได้ ก่อนนำไปใช้",
    Preview: CvPreview,
  },
  {
    title: "โปรไฟล์ที่มีหลักฐาน",
    body: "ทุกทักษะบอกที่มา คุณลบหรือแก้ไขได้ตลอดเวลา",
    Preview: EvidencePreview,
  },
  {
    title: "เทียบกับสายงาน IT",
    body: "ดูสายงานที่ใกล้เคียงที่สุด พร้อมเหตุผลของคะแนนแต่ละส่วน",
    Preview: RolesPreview,
  },
  {
    title: "รู้ว่าควรเติมอะไร",
    body: "ทักษะที่ยังขาดพร้อมขั้นตอนถัดไป และเงินเดือนอ้างอิงในกรุงเทพฯ",
    Preview: GapPreview,
  },
];

// Work-style avatar showcase (docs/WorkStyleAvatar.md). Sample answers only;
// no type names or captions such as "you are curious" (PRD FR-7, FR-17).
const AVATAR_SAMPLES = [
  { teamwork: 1, structure: 3, ambiguity: 1, pressure: 1, innovation: 1, leadership: 1 },
  { teamwork: 5, structure: 5, ambiguity: 2, pressure: 2, innovation: 3, leadership: 5 },
  { teamwork: 3, structure: 2, ambiguity: 3, pressure: 3, innovation: 4, leadership: 3 },
  { teamwork: 4, structure: 4, ambiguity: 5, pressure: 4, innovation: 2, leadership: 2 },
  { teamwork: 2, structure: 1, ambiguity: 4, pressure: 5, innovation: 5, leadership: 4 },
];

const AVATAR_PARTS = [
  { question: "ทำงานคนเดียวหรือกับทีม", part: "รูปร่าง" },
  { question: "ชอบยืดหยุ่นหรือมีขั้นตอน", part: "ทรงผม" },
  { question: "โจทย์ชัดหรือค้นหาเอง", part: "ใบหน้า" },
  { question: "จังหวะสม่ำเสมอหรือเร่งด่วน", part: "สี" },
  { question: "วิธีที่พิสูจน์แล้วหรือวิธีใหม่", part: "ของข้างตัว" },
  { question: "ทำส่วนของตัวเองหรือนำทีม", part: "ท่าแขน" },
];

const PRIVACY = [
  "ขอความยินยอมก่อนเริ่ม",
  "ใช้เพื่อแนะนำสายงานเท่านั้น",
  "ตรวจสอบและแก้ไขได้",
  "ลบทักษะที่ไม่ต้องการ",
  "ลบข้อมูลทั้งหมดได้",
  "ผู้ดูแลเห็นเฉพาะภาพรวม",
];

function SectionHeading({ eyebrow, title, children }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="text-tiny font-semibold tracking-[0.12em] text-accent uppercase">{eyebrow}</p>
      <h2 className="mt-3 text-h1 font-bold text-text md:text-[40px] md:leading-[56px]">{title}</h2>
      {children && <p className="mt-3 text-body text-text-muted">{children}</p>}
    </div>
  );
}

function Hero() {
  return (
    <section className="bg-brand-gradient relative isolate overflow-hidden">
      <ShaderBackground colors={BRAND_SILK} className="absolute inset-0 -z-10" />
      <div className="hero-scrim absolute inset-0 -z-10" aria-hidden="true" />
      <DotGrid vertical="top" className="-z-10" />

      <div className="mx-auto max-w-[1120px] px-4 pt-20 text-center md:px-6 md:pt-28">
        <p className="text-small font-semibold text-hero-muted">รู้จักตัวเอง ก่อนเลือกสายงาน IT</p>
        <h1 className="mx-auto mt-4 max-w-3xl text-[36px] leading-[52px] font-bold text-hero-fg md:text-hero">
          เข้าใจตัวเองก่อน
          <br />
          แล้วงานที่ใช่จะชัดขึ้น
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-body text-hero-muted">
          สะท้อนจุดแข็ง ทักษะที่ควรเติม และสายงานที่เหมาะ จากเรื่องราวและประสบการณ์ของคุณ
        </p>
        <HeroActions />
      </div>

      {/* Floating preview cards over the horizon */}
      <div className="relative mx-auto mt-16 h-[420px] max-w-[1120px] md:mt-20 md:h-[400px]">
        <div className="hero-glow absolute top-0 left-1/2 size-[620px] -translate-x-1/2" aria-hidden="true" />
        <div className="relative z-10 flex flex-col items-center gap-4 md:flex-row md:justify-center md:gap-10">
          <ProfileCard className="animate-float -rotate-6 md:mt-10" />
          <MatchCard className="animate-float-slow hidden rotate-6 sm:block" />
        </div>
        <div
          className="horizon absolute top-[150px] left-1/2 aspect-square w-[1500px] -translate-x-1/2 rounded-full md:top-[190px] md:w-[1900px]"
          aria-hidden="true"
        />
      </div>
    </section>
  );
}

function Features() {
  return (
    <section className="mx-auto w-full max-w-[1120px] px-4 py-20 md:px-6">
      <SectionHeading eyebrow="ภาพรวม" title="เห็นตัวเองชัดขึ้น ก่อนตัดสินใจ">
        CareerMirror ไม่ได้บอกว่าคุณควรเป็นอะไร แต่ช่วยให้คุณเห็นสิ่งที่มีอยู่แล้วอย่างชัดเจน
      </SectionHeading>
      <ul className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map(({ title, body, Preview }) => (
          // Hover: the card lifts a little, the preview inside floats up and grows,
          // tilted previews straighten (straight ones tilt), and the glow brightens.
          <li
            key={title}
            className="group/feature rounded-xl border border-border bg-surface p-2 shadow-sm transition-[transform,box-shadow] duration-300 ease-out hover:-translate-y-1 hover:shadow-md"
          >
            <Thumb className="h-44">
              <div className="transition-transform duration-500 ease-out group-hover/feature:-translate-y-2 group-hover/feature:scale-[1.06]">
                <Preview />
              </div>
            </Thumb>
            <div className="px-3 pt-4 pb-3">
              <h3 className="text-h3 font-semibold text-text">{title}</h3>
              <p className="mt-1 text-small text-text-muted">{body}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function AvatarShowcase() {
  return (
    <section className="mx-auto w-full max-w-[1120px] px-4 pb-20 md:px-6">
      <SectionHeading eyebrow="ตัวละครของคุณ" title="ตัวละครที่ประกอบจากคำตอบของคุณ">
        ตอบ 6 ข้อเรื่องความชอบในการทำงาน แต่ละคำตอบเปลี่ยนตัวละครหนึ่งส่วน ไม่มีแบบไหนดีกว่ากัน
      </SectionHeading>
      <div className="mt-12 grid items-center gap-8 rounded-xl border border-border bg-surface p-6 shadow-sm md:p-10 lg:grid-cols-[1.3fr_1fr]">
        <div>
          <ul className="flex items-end justify-center gap-2 sm:gap-4" aria-label="ตัวอย่างตัวละคร">
            {AVATAR_SAMPLES.map((steps, i) => (
              <li key={i} className={`${i % 2 ? "mb-6" : ""} ${i >= 3 ? "hidden sm:block" : ""}`}>
                <WorkStyleAvatar steps={steps} size={112} delay={i * 0.7} decorative />
              </li>
            ))}
          </ul>
          <p className="mt-4 text-center text-small text-text-muted">
            ตัวอย่างตัวละคร · ประกอบได้ <span className="tabular">15,625</span> แบบ
          </p>
        </div>
        <div>
          <ol className="space-y-2">
            {AVATAR_PARTS.map(({ question, part }, i) => (
              <li key={part} className="flex items-center gap-3 text-small">
                <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-subtle font-semibold text-text tabular">
                  {i + 1}
                </span>
                <span className="text-text-muted">{question}</span>
                <ArrowRight className="size-3.5 shrink-0 text-text-muted" strokeWidth={2} aria-hidden="true" />
                <span className="font-semibold text-text">{part}</span>
              </li>
            ))}
          </ol>
          <ul className="mt-6 space-y-2">
            {["ทุกส่วนบอกได้ว่ามาจากคำตอบข้อไหน", "เปลี่ยนคำตอบเมื่อไร ตัวละครก็เปลี่ยนตาม"].map((c) => (
              <li key={c} className="flex items-start gap-2 text-small text-text-muted">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" strokeWidth={1.5} aria-hidden="true" />
                {c}
              </li>
            ))}
          </ul>
          <p className="mt-5 text-tiny text-info">ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ</p>
        </div>
      </div>
    </section>
  );
}

function Steps() {
  return (
    <section className="mx-auto w-full max-w-[1120px] px-4 pb-20 md:px-6">
      <SectionHeading eyebrow="ขั้นตอน" title="4 ขั้นตอน สู่ก้าวถัดไปที่ชัดเจน">
        ทำตามลำดับหรือข้ามไปมาได้ ข้อมูลของคุณบันทึกไว้ให้เสมอ
      </SectionHeading>
      <StepsTimeline />
    </section>
  );
}

// Role names come from the same role files the matching uses (web/lib/mock/fixtures/roles.json,
// generated from data/roles); only the fields the section shows are passed to the client.
const ROLES = ROLE_FILES.map(({ role_id, title_th, title_en, career_stage }) => ({ role_id, title_th, title_en, career_stage }));

function Roles() {
  return (
    <section className="mb-20" aria-label="สายงานที่รองรับ">
      <RolesShowcase roles={ROLES} />
    </section>
  );
}

function Privacy() {
  return (
    <section className="mx-auto w-full max-w-[1120px] px-4 pb-20 md:px-6">
      <div className="bg-brand-gradient relative isolate overflow-hidden rounded-xl px-6 py-10 md:px-12 md:py-14">
        <ShaderBackground colors={BRAND_SILK} className="absolute inset-0 -z-10" />
        <div className="hero-scrim absolute inset-0 -z-10" aria-hidden="true" />
        <DotGrid intensity={0.5} clear={0.6} className="-z-10" />
        <div
          className="horizon absolute top-[55%] -right-[260px] -z-10 aspect-square w-[620px] rounded-full md:top-[35%]"
          aria-hidden="true"
        />
        <div className="max-w-xl">
          <p className="text-tiny font-semibold tracking-[0.12em] text-hero-muted uppercase">ความเป็นส่วนตัว</p>
          <h2 className="mt-3 text-h1 font-bold text-hero-fg">คุณเป็นเจ้าของเรื่องราวของคุณ</h2>
          <p className="mt-2 text-body text-hero-muted">
            ข้อมูลใช้เพื่อแนะนำสายงานเท่านั้น คุณตรวจสอบ แก้ไข และลบได้ทุกเมื่อ
          </p>
          <ul className="mt-8 flex flex-wrap gap-2">
            {PRIVACY.map((p) => (
              <li key={p} className="glass rounded-full px-4 py-1.5 text-small text-text">
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div
          className="glass animate-float absolute top-10 right-10 hidden rotate-6 flex-col items-center gap-2 rounded-xl px-6 py-5 lg:flex"
          aria-hidden="true"
        >
          <ShieldCheck className="size-9 text-primary" strokeWidth={1.5} />
          <span className="text-h3 font-semibold text-text">ข้อมูลของคุณ</span>
        </div>
      </div>
    </section>
  );
}

const CREATORS = [
  { name: "พัลลภ บุญเหลือ", photo: "/creators/phanlop.jpg" },
  { name: "ศักดา เบ้าคำ", photo: "/creators/sakda.jpg" },
];

function Creators() {
  return (
    <section className="mx-auto w-full max-w-[1120px] px-4 pb-20 md:px-6" aria-labelledby="creators">
      <div className="mx-auto max-w-2xl text-center">
        <p className="text-tiny font-semibold tracking-[0.12em] text-accent uppercase">ผู้พัฒนา</p>
        <h2 id="creators" className="mt-3 text-h1 font-bold text-text md:text-[40px] md:leading-[56px]">
          ทีมผู้สร้าง CareerMirror
        </h2>
        <p className="mt-3 inline-flex items-center gap-2 text-body text-text-muted">
          <GraduationCap className="size-5 text-accent" strokeWidth={1.75} aria-hidden="true" />
          Advanced Topics in Computer Software · RMUTT
        </p>
      </div>
      <ul className="mx-auto mt-10 grid max-w-2xl gap-5 sm:grid-cols-2">
        {CREATORS.map(({ name, photo }) => (
          <li key={name} className="group relative flex flex-col items-center overflow-hidden rounded-xl border border-border bg-glass p-8 text-center shadow-sm transition-[transform,box-shadow] duration-300 ease-out hover:-translate-y-1 hover:shadow-md">
            <div className="bg-brand-gradient absolute inset-x-0 top-0 h-24 opacity-90" aria-hidden="true" />
            <Image
              src={photo}
              alt={`รูปของ${name}`}
              width={240}
              height={240}
              sizes="128px"
              className="relative mt-2 size-32 rounded-full object-cover shadow-md ring-4 ring-bg transition-transform duration-300 ease-out group-hover:scale-105"
            />
            <p className="relative mt-4 text-h3 font-semibold text-text">{name}</p>
            <p className="relative mt-1 text-small text-text-muted">ผู้พัฒนา CareerMirror</p>
          </li>
        ))}
      </ul>
      <div className="mt-8 text-center">
        <Link
          href="/present"
          className="inline-flex min-h-11 items-center gap-2 rounded-full border border-border bg-glass px-5 text-small font-semibold text-text shadow-sm transition-colors duration-200 ease-out hover:border-primary"
        >
          <Presentation className="size-4 text-accent" strokeWidth={1.75} aria-hidden="true" />
          ดูการนำเสนอโปรเจกต์
        </Link>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="bg-brand-gradient relative isolate overflow-hidden">
      <ShaderBackground colors={BRAND_SILK} className="absolute inset-0 -z-10" />
      <div className="hero-scrim absolute inset-0 -z-10" aria-hidden="true" />
      <DotGrid vertical="top" className="-z-10" />
      <div className="mx-auto max-w-[1120px] px-4 pt-20 pb-40 text-center md:px-6 md:pb-48">
        <Eye className="mx-auto size-8 text-hero-muted" strokeWidth={1.5} aria-hidden="true" />
        <h2 className="mx-auto mt-4 max-w-2xl text-h1 font-bold text-hero-fg md:text-[40px] md:leading-[56px]">
          เริ่มจากสิ่งที่คุณมีอยู่แล้ว
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-body text-hero-muted">
          อัปโหลด CV หรือตอบแบบสอบถาม แล้วดูว่าทักษะของคุณเหมาะกับสายงาน IT แบบไหน
        </p>
        <FinalAction />
      </div>
      <div
        className="horizon absolute top-[calc(100%-110px)] left-1/2 aspect-square w-[1500px] -translate-x-1/2 rounded-full md:w-[1900px]"
        aria-hidden="true"
      />
    </section>
  );
}

function Footer() {
  return (
    <footer className="mx-auto flex w-full max-w-[1120px] flex-col gap-2 px-4 py-8 text-small text-text-muted md:flex-row md:justify-between md:px-6">
      <p>
        CareerMirror · พัฒนาโดย พัลลภ บุญเหลือ และ ศักดา เบ้าคำ ·{" "}
        <Link href="/present" className="font-semibold text-accent hover:underline">
          การนำเสนอโปรเจกต์
        </Link>
      </p>
      <p>คำแนะนำช่วยสำรวจทางเลือก ไม่รับประกันการได้งาน</p>
    </footer>
  );
}

export default function Home() {
  return (
    <>
      <Hero />
      <div className="bg-section-wash">
        <Features />
        <Roles />
        <AvatarShowcase />
        <Steps />
        <Privacy />
        <Creators />
      </div>
      <FinalCta />
      <Footer />
    </>
  );
}
