import {
  ArrowDown,
  ChevronDown,
  Compass,
  ExternalLink,
  MapPin,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { SiteHeader } from "@/components/site-header";
import { TravelForm } from "@/components/travel-form";
import { RoutePreview } from "@/components/route-preview";
import { RecommendationDashboard } from "@/components/recommendation-dashboard";
import { TravelAssistantDrawer } from "@/components/travel-assistant-drawer";

const faqs = [
  [
    "ข้อมูลอัปเดตแบบ Real-time แค่ไหน?",
    "เมื่อสร้างคำขอ ระบบรับสัญญาณล่าสุดจากแหล่งข้อมูลที่เชื่อมต่อ (Longdo Traffic / iTIC, TomTom, Open-Meteo, ข้อมูลภัยพิบัติ) และแสดงเวลาอัปเดตในแต่ละเหตุผลอย่างโปร่งใส",
  ],
  [
    "WayPoint ตัดสินใจแทนฉันหรือไม่?",
    "ระบบประเมินความเสี่ยง นำเสนอระดับความเสี่ยง (LOW, MEDIUM, HIGH) พร้อมเหตุผลและเส้นทางทางเลือก เพื่อให้ผู้เดินทางใช้ประกอบการตัดสินใจด้วยตนเอง",
  ],
  [
    "ระบบแม่นยำ 100% หรือไม่?",
    "ข้อมูลภายนอกและสภาพพื้นที่จริงอาจเปลี่ยนแปลงได้ตลอดเวลา คำแนะนำจึงเป็นข้อมูลช่วยตัดสินใจตามสัญญาณข้อมูลล่าสุด ไม่ใช่การรับประกันความปลอดภัยเชิงกายภาพ",
  ],
  [
    "ตำแหน่งของฉันถูกเก็บไว้หรือไม่?",
    "ระบบใช้พิกัดตำแหน่งเฉพาะสำหรับประมวลผลความปลอดภัยของเส้นทางที่ระบุเท่านั้น โดยเป็นไปตามนโยบายความเป็นส่วนตัว",
  ],
];

export default function Home() {
  return (
    <main id="top" className="overflow-hidden bg-cloud">
      {/* 1. Hero & Travel Planning Form */}
      <section aria-label="Plan your journey" className="relative min-h-[850px] overflow-hidden text-white">
        <div aria-hidden className="hero-photo hero-motion absolute -inset-8" />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-[#03162c]/88 via-[#03162c]/55 to-[#03162c]/25" />
        <SiteHeader />
        <div className="relative z-10 mx-auto grid min-h-[850px] max-w-7xl items-center gap-12 px-6 pb-14 pt-32 lg:grid-cols-[1.1fr_.9fr] lg:pb-20">
          <div className="max-w-2xl">
            <p className="mb-6 flex items-center gap-2 text-xs font-bold tracking-[.22em] text-white/80">
              <span className="h-px w-10 bg-white/70" /> AI-POWERED TRAVEL SAFETY
            </p>
            <h1 className="font-display text-5xl leading-[.95] sm:text-7xl lg:text-8xl">
              Travel smart.<br />
              <i className="font-normal text-[#b9e5fb]">Know the risk.</i>
            </h1>
            <p className="mt-7 max-w-md text-base leading-7 text-white/85">
              วางแผนและประเมินความปลอดภัยการเดินทางล่วงหน้า ด้วยระบบ Agentic AI วิเคราะห์สภาพอากาศ สภาพจราจรสด และการแจ้งเตือนภัยพิบัติแบบเรียลไทม์
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <a
                href="#map"
                className="inline-flex items-center gap-2 rounded-full bg-white/10 px-5 py-2.5 text-xs font-bold tracking-widest text-white backdrop-blur transition hover:bg-white/20"
              >
                <MapPin size={15} /> VIEW ROUTE MAP
              </a>
              <a
                href="#dashboard"
                className="inline-flex items-center gap-2 rounded-full bg-aqua px-5 py-2.5 text-xs font-bold tracking-widest text-white transition hover:bg-aqua/90"
              >
                <ShieldCheck size={15} /> SAFETY DASHBOARD <ArrowDown size={14} />
              </a>
            </div>
          </div>
          <div className="rounded-[1.35rem] border border-white/80 bg-white/95 p-5 text-ink shadow-float backdrop-blur sm:p-7">
            <div className="mb-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-bold tracking-[.16em] text-aqua">TRIP SAFETY CHECK</p>
                <h2 className="mt-1 font-display text-3xl">ตรวจสอบความปลอดภัยเส้นทาง</h2>
              </div>
              <span className="rounded-full bg-[#e7f4fb] p-2 text-aqua">
                <Sparkles size={18} />
              </span>
            </div>
            <TravelForm />
          </div>
        </div>
      </section>

      {/* 2. Interactive Route Map Preview */}
      <section id="map" className="bg-white px-6 py-20 sm:py-28">
        <div className="mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[.8fr_1.2fr]">
          <div>
            <p className="text-xs font-bold tracking-[.2em] text-aqua">YOUR ROUTE, IN CONTEXT</p>
            <h2 className="mt-4 font-display text-4xl leading-tight sm:text-5xl">
              ตรวจสอบเส้นทาง<br />และพิกัดบนแผนที่
            </h2>
            <p className="mt-6 max-w-sm text-sm leading-7 text-slate-600">
              ยืนยันหมุดต้นทาง ปลายทาง และตรวจสอบภาพรวมเส้นทางบนแผนที่แบบอินเทอร์แอคทีฟ เพื่อให้ผลการประเมินความเสี่ยงตรงกับเส้นทางจริงของคุณ
            </p>
            <div className="mt-8 flex gap-8 border-l-2 border-aqua pl-5 text-sm">
              <span>
                <b className="block text-ink">Leaflet + Longdo Map</b>
                <span className="text-slate-500">Live Map Layer</span>
              </span>
              <span>
                <b className="block text-ink">Valhalla Road Routes</b>
                <span className="text-slate-500">Geometry Preview</span>
              </span>
            </div>
          </div>
          <RoutePreview />
        </div>
      </section>

      {/* 3. Real-Time Recommendation Dashboard */}
      <section id="dashboard" className="bg-ink px-6 py-20 text-white sm:py-28">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
            <div>
              <p className="text-xs font-bold tracking-[.2em] text-[#a9dbf5]">REAL-TIME SAFETY INTELLIGENCE</p>
              <h2 className="mt-4 font-display text-4xl leading-tight sm:text-5xl">
                ผลการประเมินและคำแนะนำ<br />
                <i className="font-normal text-[#b9e5fb]">Recommendation Dashboard</i>
              </h2>
            </div>
            <p className="max-w-sm text-sm leading-6 text-white/65">
              แสดงระดับความเสี่ยง สภาพอากาศ สภาพการจราจรสด การแจ้งเตือนภัยพิบัติ และความสดใหม่ของข้อมูล
            </p>
          </div>
          <div className="mt-12">
            <RecommendationDashboard />
          </div>
        </div>
      </section>

      {/* 4. FAQ Section */}
      <section id="faq" className="paper-grid px-6 py-20 sm:py-28">
        <div className="mx-auto grid max-w-5xl gap-12 lg:grid-cols-[.8fr_1.2fr]">
          <div>
            <p className="text-xs font-bold tracking-[.2em] text-aqua">FREQUENTLY ASKED</p>
            <h2 className="mt-4 font-display text-4xl leading-tight sm:text-5xl">
              คำถามที่พบบ่อย
            </h2>
            <p className="mt-6 text-sm leading-6 text-slate-600">
              รายละเอียดการทำงานและความโปร่งใสของระบบประเมินความปลอดภัย
            </p>
          </div>
          <div className="divide-y divide-ink/15 border-y border-ink/15">
            {faqs.map(([q, a], i) => (
              <details key={q} className="group py-5" open={i === 0}>
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-bold">
                  {q}
                  <ChevronDown className="shrink-0 transition group-open:rotate-180" size={18} />
                </summary>
                <p className="max-w-xl pt-3 text-sm leading-6 text-slate-600">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* 5. Footer */}
      <footer className="bg-ink px-6 py-12 text-white">
        <div className="mx-auto grid max-w-7xl gap-10 md:grid-cols-4">
          <div className="md:col-span-2">
            <div className="flex items-center gap-2 text-xl font-bold">
              <Compass /> WayPoint
            </div>
            <p className="mt-4 max-w-sm text-sm leading-6 text-white/65">
              ระบบประเมินความปลอดภัยการเดินทางอัจฉริยะ (AI-Powered Travel Safety Assessment Platform)
            </p>
          </div>
          <div>
            <p className="text-xs font-bold tracking-widest text-white/45">เบอร์โทรติดต่อฉุกเฉิน</p>
            <p className="mt-3 text-sm leading-7">
              <a href="tel:191" className="hover:underline">191 เหตุด่วนเหตุร้าย (ตำรวจ)</a><br />
              <a href="tel:1669" className="hover:underline">1669 ศูนย์กู้ชีพและแพทย์ฉุกเฉิน</a><br />
              <a href="tel:1193" className="hover:underline">1193 ตำรวจทางหลวง</a><br />
              <a href="tel:1784" className="hover:underline">1784 สายด่วน ปภ. (เตือนภัยพิบัติ)</a>
            </p>
          </div>
          <div>
            <p className="text-xs font-bold tracking-widest text-white/45">ระบบและบริการ</p>
            <p className="mt-3 text-sm leading-7 text-white/75">
              <a href="#dashboard" className="hover:underline">แดชบอร์ดความปลอดภัย</a><br />
              <a href="/status" className="hover:underline">สถานะระบบ (Service Status)</a><br />
              <a href="#faq" className="hover:underline">คำถามที่พบบ่อย (FAQ)</a><br />
              <a href="/admin" className="hover:underline">ระบบผู้ดูแล (Admin Console) <ExternalLink className="inline" size={12} /></a>
            </p>
          </div>
        </div>
        <div className="mx-auto mt-12 flex max-w-7xl flex-col gap-3 border-t border-white/15 pt-5 text-xs text-white/45 md:flex-row md:justify-between">
          <span>© 2026 WayPoint. Travel Safety Assessment System.</span>
          <span>ข้อมูลใช้เพื่อประกอบการตัดสินใจ โปรดตรวจสอบประกาศทางการก่อนออกเดินทาง</span>
        </div>
      </footer>

      <TravelAssistantDrawer />
    </main>
  );
}
