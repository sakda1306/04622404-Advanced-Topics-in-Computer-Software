"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, Compass, Flag, Info, Lightbulb, ListChecks, Quote, Timer, Users } from "lucide-react";
import { Cite } from "@/components/app/citation";
import { Card } from "@/components/intake/ui";
import { AVATAR_CAPTION_TH, AvatarProgress, WorkStyleAvatar } from "@/components/avatar/work-style-avatar";
import { AVATAR_TRAITS, answeredCount, avatarSwatch, stepsFromWorkStyle } from "@/lib/avatar";

// "ความชอบในการทำงาน" (FR-16): the character, a one-quote summary and six trait
// tiles. A tile shows an icon, a short tag and where the answer sits on its
// scale; tapping it opens the full sentence, both ends of the scale and the
// avatar part it drives. The self-report disclaimer stays visible (CONVENTIONS:
// preferences, not a personality diagnosis).

const TRAITS = {
  teamwork: { Icon: Users, topic: "การทำงานกับทีม", tags: ["ชอบลุยเดี่ยว", "ชอบทำเป็นทีม"], ends: ["ทำงานคนเดียวเป็นหลัก", "ทำงานร่วมกับทีมตลอด"] },
  structure: { Icon: ListChecks, topic: "วิธีทำงาน", tags: ["ยืดหยุ่น คิดเอง", "มีขั้นตอนชัด"], ends: ["คิดวิธีทำเองอย่างยืดหยุ่น", "มีขั้นตอนและมาตรฐานชัดเจน"] },
  ambiguity: { Icon: Compass, topic: "โจทย์ที่ชอบ", tags: ["โจทย์ชัดเจน", "โจทย์เปิด"], ends: ["อยากได้โจทย์ชัดก่อนเริ่ม", "สนุกกับการค้นหาคำตอบเอง"] },
  pressure: { Icon: Timer, topic: "จังหวะงาน", tags: ["จังหวะสม่ำเสมอ", "ชอบงานเร่ง"], ends: ["จังหวะสม่ำเสมอ วางแผนได้", "งานเร่งด่วน เดดไลน์กระชั้น"] },
  innovation: { Icon: Lightbulb, topic: "เครื่องมือและวิธี", tags: ["วิธีที่พิสูจน์แล้ว", "ชอบลองของใหม่"], ends: ["ใช้วิธีที่พิสูจน์แล้ว", "ลองวิธีหรือเครื่องมือใหม่ ๆ"] },
  leadership: { Icon: Flag, topic: "บทบาทในทีม", tags: ["โฟกัสงานตัวเอง", "ชอบนำทีม"], ends: ["รับผิดชอบงานส่วนของตัวเอง", "นำทีมและประสานงาน"] },
};

/** Short tag for a 0..1 value: one end, or "สมดุล" in the middle. */
function tagOf(key, value) {
  const [low, high] = TRAITS[key].tags;
  if (value < 0.4) return low;
  if (value > 0.6) return high;
  return "สมดุลทั้งสองแบบ";
}

function MiniScale({ value }) {
  return (
    <span className="relative mt-2 block h-1.5 rounded-full bg-border" aria-hidden="true">
      <span className="absolute inset-y-0 left-0 rounded-full bg-primary/30" style={{ width: `${value * 100}%` }} />
      <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-primary" style={{ left: `${value * 100}%` }} />
    </span>
  );
}

function TraitTile({ trait, step }) {
  const meta = TRAITS[trait.trait];
  if (!meta) return null;
  const { Icon } = meta;
  const avatarPart = AVATAR_TRAITS.find((t) => t.key === trait.trait);
  return (
    <li>
      <details className="group rounded-lg border border-border bg-bg transition-colors duration-150 open:border-primary/40 open:bg-surface hover:border-primary/40">
        <summary className="flex min-h-11 cursor-pointer list-none items-start gap-3 rounded-lg p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary [&::-webkit-details-marker]:hidden">
          <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-primary-subtle text-primary">
            <Icon className="size-4.5" strokeWidth={2} aria-hidden="true" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-tiny text-text-muted">{meta.topic}</span>
            <span className="block text-small font-semibold text-text">{tagOf(trait.trait, trait.value)}</span>
            <MiniScale value={trait.value} />
          </span>
          <ChevronDown className="mt-1 size-4 shrink-0 text-text-muted transition-transform duration-200 group-open:rotate-180" strokeWidth={2} aria-hidden="true" />
          <span className="sr-only">ดูรายละเอียด</span>
        </summary>
        <div className="space-y-2 border-t border-border px-3 pt-2.5 pb-3 text-small">
          <p className="text-text">
            {trait.label_th}
            <Cite ids={trait.evidence_ids} />
          </p>
          <p className="flex justify-between gap-3 text-tiny text-text-muted">
            <span>{meta.ends[0]}</span>
            <span className="text-right">{meta.ends[1]}</span>
          </p>
          {avatarPart && step != null && (
            <p className="flex items-center gap-1.5 text-tiny text-text-muted">
              {trait.trait === "pressure" && (
                <span className="inline-block size-3 rounded-full border border-text/60" style={{ background: avatarSwatch(step) }} aria-hidden="true" />
              )}
              ในตัวละคร: {avatarPart.part_th} · <span className="font-medium text-text">{avatarPart.names_th[step - 1]}</span>
            </p>
          )}
        </div>
      </details>
    </li>
  );
}

export function SummaryQuote({ text, ids }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  const long = text.length > 140;
  return (
    <div className="relative mt-5 w-full rounded-lg bg-primary-subtle/60 px-4 pt-3 pb-3 backdrop-blur-md text-left @lg:mt-0 @3xl:mt-5">
      <Quote className="absolute -top-2.5 left-3 size-5 fill-current text-accent" strokeWidth={1.5} aria-hidden="true" />
      <blockquote className={`text-small text-text ${long && !open ? "line-clamp-3" : ""}`}>
        {text}
        <Cite ids={ids} />
      </blockquote>
      {long && (
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="mt-1 text-tiny font-semibold text-accent hover:underline">
          {open ? "ย่อ" : "อ่านต่อ"}
        </button>
      )}
    </div>
  );
}

/** The six trait tiles on their own (the profile dashboard puts them in a tile). */
export function WorkStyleTraits({ workStyle, values, className = "" }) {
  const steps = stepsFromWorkStyle(values);
  const traits = workStyle.traits.filter((t) => TRAITS[t.trait]);
  if (!traits.length) return <p className="text-small text-text-muted">ยังไม่มีคำตอบเรื่องความชอบในการทำงาน</p>;
  return (
    <ul className={`grid items-start gap-2.5 @md:grid-cols-2 ${className}`}>
      {traits.map((t) => (
        <TraitTile key={t.trait} trait={t} step={steps[t.trait]} />
      ))}
    </ul>
  );
}

/** Short tag per trait for chips, e.g. "ชอบทำเป็นทีม". */
export function traitTags(workStyle) {
  return workStyle.traits.filter((t) => TRAITS[t.trait]).map((t) => ({ trait: t.trait, Icon: TRAITS[t.trait].Icon, tag: tagOf(t.trait, t.value), topic: TRAITS[t.trait].topic }));
}

export function WorkStyleCard({ workStyle, values }) {
  const steps = stepsFromWorkStyle(values);
  const traits = workStyle.traits.filter((t) => TRAITS[t.trait]);
  return (
    <Card title="ความชอบในการทำงาน" subtitle="จากคำตอบที่คุณเลือกเอง · แตะแต่ละข้อเพื่อดูรายละเอียด">
      {/* Sized by the card, not the window: the chat panel narrows the card at lg. */}
      <div className="@container">
        <div className="grid gap-6 @3xl:grid-cols-[minmax(0,220px)_1fr] @3xl:items-start">
          <figure className="flex flex-col items-center gap-x-6 text-center @lg:flex-row @lg:items-center @lg:text-left @3xl:flex-col @3xl:text-center">
            <div className="flex shrink-0 flex-col items-center text-center">
              <WorkStyleAvatar steps={steps} size={168} />
              <figcaption className="mt-2 max-w-[200px] text-tiny text-text-muted">{AVATAR_CAPTION_TH}</figcaption>
              <AvatarProgress steps={steps} className="mt-1" />
              {answeredCount(steps) === 0 && (
                <Link href="/start?tab=questionnaire" className="mt-1 text-small font-semibold text-accent hover:underline">
                  ตอบ 6 ข้อนี้เพื่อสร้างตัวละครของคุณ
                </Link>
              )}
            </div>
            <SummaryQuote text={workStyle.summary_th} ids={workStyle.summary_evidence_ids} />
          </figure>

          {traits.length > 0 ? (
            <ul className="grid items-start gap-2.5 @md:grid-cols-2">
            {traits.map((t) => (
                <TraitTile key={t.trait} trait={t} step={steps[t.trait]} />
              ))}
            </ul>
          ) : (
            <p className="text-small text-text-muted">ยังไม่มีคำตอบเรื่องความชอบในการทำงาน</p>
          )}
        </div>
      </div>
      <p className="mt-5 flex items-start gap-2 text-tiny text-info">
        <Info className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
        <span>{workStyle.disclaimer_th}</span>
      </p>
    </Card>
  );
}
