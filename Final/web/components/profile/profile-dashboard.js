"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, BadgeCheck, Briefcase, Code2, FileSearch, Handshake, Info, Lightbulb, Quote, Sparkles, UsersRound } from "lucide-react";
import { Cite } from "@/components/app/citation";
import { Pill, ShareStrip, Tile, pct } from "@/components/app/bento";
import { AVATAR_CAPTION_TH, AvatarProgress, WorkStyleAvatar } from "@/components/avatar/work-style-avatar";
import { DotGrid } from "@/components/motion/dot-grid";
import { LEVELS, levelLabel } from "@/components/intake/ui";
import { WorkStyleTraits, traitTags } from "@/components/profile/work-style-card";
import { stepsFromWorkStyle } from "@/lib/avatar";
import { useCountUp, useEntered } from "@/lib/use-motion";

// Profile page as a bento dashboard (DesignSystem.md section 4). Tiles: three
// KPIs, the work-style character (tall), skill strength, skills per level, a
// highlight card, the six work-style traits, evidence sources, things to explore
// and experience. Every number comes from the profile itself; notes say they are
// worked out from it. Claims keep their citations [n].

export function monthsTh(total) {
  if (!total) return null;
  const y = Math.floor(total / 12);
  const m = total % 12;
  return [y ? `${y} ปี` : "", m ? `${m} เดือน` : ""].filter(Boolean).join(" ");
}

export function Disclaimer({ children }) {
  return (
    <p className="mt-4 flex items-start gap-2 text-tiny text-info">
      <Info className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

export function ClaimList({ claims, empty }) {
  if (!claims?.length) return <p className="text-small text-text-muted">{empty}</p>;
  return (
    <ul className="space-y-3.5">
      {claims.map((c, i) => (
        <li key={i} className="flex gap-2.5 text-small leading-6 text-text">
          <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
          <span>
            {c.text_th}
            <Cite ids={c.evidence_ids} />
            {c.edited_by_user && <span className="ml-1 rounded-full bg-primary-subtle px-2 py-0.5 text-tiny font-medium">แก้ไขโดยคุณ</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

const strong = (skills) => skills.filter((s) => s.level >= 3);

/* ---------- KPIs ---------- */

function Kpi({ icon, title, value, unit, children }) {
  return (
    <Tile title={title} icon={icon}>
      <div className="mt-auto flex flex-wrap items-end gap-x-3 gap-y-2">
        <p className="tabular font-[family-name:var(--font-latin-first)] text-[44px] leading-none font-semibold tracking-tight text-text">
          {value}
          {unit && <span className="ml-1.5 text-h3 font-medium text-text-muted">{unit}</span>}
        </p>
        <div className="mb-1">{children}</div>
      </div>
    </Tile>
  );
}

export function KpiTiles({ profile }) {
  const hard = useCountUp(profile.hard_skills.length);
  const soft = useCountUp(profile.soft_skills.length);
  const months = profile.experience.total_months;
  const years = months ? months / 12 : 0;
  return (
    <>
      <Kpi icon={Code2} title="ทักษะด้านเทคนิค" value={Math.round(hard)} unit="ทักษะ">
        <Pill ok>{strong(profile.hard_skills).length} ทักษะระดับคล่องขึ้นไป</Pill>
      </Kpi>
      <Kpi icon={Handshake} title="ทักษะการทำงานร่วมกับผู้อื่น" value={Math.round(soft)} unit="ทักษะ">
        <span className="text-tiny text-text-muted">จากคะแนน 4–5 และตัวอย่างที่เล่า</span>
      </Kpi>
      <Kpi icon={Briefcase} title="ประสบการณ์รวม" value={months ? (years >= 1 ? years.toFixed(years % 1 ? 1 : 0) : months) : "–"} unit={months ? (years >= 1 ? "ปี" : "เดือน") : ""}>
        <span className="text-tiny text-text-muted">{months ? `ประมาณ ${monthsTh(months)}` : "ยังไม่มีข้อมูล"}</span>
      </Kpi>
    </>
  );
}

/* ---------- character ---------- */

// The character's own line, first person, from the user's clearest leanings
// (the traits furthest from the middle). Each end of a trait has one phrase.
const MOTTO = {
  teamwork: ["ชอบลุยงานเดี่ยวแบบโฟกัส", "ชอบลุยงานไปพร้อมทีม"],
  structure: ["ชอบคิดวิธีใหม่ด้วยตัวเอง", "ชอบงานที่มีขั้นตอนชัดเจน"],
  ambiguity: ["อยากเห็นโจทย์ชัดก่อนลงมือ", "สนุกกับโจทย์ที่ยังไม่มีคำตอบ"],
  pressure: ["ทำงานได้ดีที่สุดเมื่อวางแผนได้", "ยิ่งงานเร่งยิ่งมีพลัง"],
  innovation: ["เชื่อในวิธีที่พิสูจน์แล้ว", "ชอบลองเครื่องมือใหม่ ๆ"],
  leadership: ["ทุ่มเทกับงานในส่วนของตัวเอง", "ชอบเป็นคนพาทีมไปข้างหน้า"],
};

function characterMotto(workStyle) {
  const clear = workStyle.traits
    .filter((t) => MOTTO[t.trait] && Math.abs(t.value - 0.5) > 0.1)
    .sort((a, b) => Math.abs(b.value - 0.5) - Math.abs(a.value - 0.5))
    .slice(0, 3);
  if (!clear.length) return { text: "ฉันปรับตัวได้กับการทำงานแทบทุกแบบ", ids: [] };
  const parts = clear.map((t) => MOTTO[t.trait][t.value > 0.5 ? 1 : 0]);
  const text = parts.length === 1 ? `ฉัน${parts[0]}` : `ฉัน${parts.slice(0, -1).join(" ")} และ${parts.at(-1)}`;
  return { text, ids: [...new Set(clear.flatMap((t) => t.evidence_ids ?? []))] };
}

function CharacterQuote({ workStyle }) {
  const { text, ids } = characterMotto(workStyle);
  return (
    <figure className="relative mt-5 w-full rounded-xl bg-primary-subtle/60 px-4 pt-4 pb-3 backdrop-blur-md text-left">
      <Quote className="absolute -top-2.5 left-3 size-5 fill-current text-accent" strokeWidth={1.5} aria-hidden="true" />
      <blockquote className="text-body leading-7 font-semibold text-text">
        “{text}”
        <Cite ids={ids} />
      </blockquote>
      <figcaption className="mt-1.5 text-tiny text-text-muted">— ตัวละครของคุณ · จากคำตอบเรื่องความชอบในการทำงาน</figcaption>
    </figure>
  );
}

export function CharacterTile({ workStyle, values }) {
  const steps = stepsFromWorkStyle(values);
  const tags = traitTags(workStyle);
  return (
    <Tile title="ตัวละครของคุณ" icon={UsersRound}>
      <figure className="flex flex-col items-center text-center">
        <WorkStyleAvatar steps={steps} size={170} />
        <figcaption className="mt-2 text-tiny text-text-muted">{AVATAR_CAPTION_TH}</figcaption>
        <AvatarProgress steps={steps} className="mt-1" />
      </figure>
      <CharacterQuote workStyle={workStyle} />
      {tags.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-1.5" aria-label="ความชอบในการทำงานโดยย่อ">
          {tags.map(({ trait, Icon, tag, topic }) => (
            <li key={trait} title={topic} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-bg/60 px-2.5 py-1 text-tiny text-text">
              <Icon className="size-3.5 text-accent" strokeWidth={2} aria-hidden="true" />
              {/* A balanced trait names its topic, so two "สมดุล" chips stay distinct. */}
              {tag === "สมดุลทั้งสองแบบ" ? `${topic}: สมดุล` : tag}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-auto">
        <Disclaimer>{workStyle.disclaimer_th}</Disclaimer>
      </div>
    </Tile>
  );
}

/* ---------- skill strength ---------- */

const SHOW_SKILLS = 9;

/** Technical skills, strongest first: a 4-step bar per skill (one hue), level in text. */
export function SkillStrengthTile({ skills }) {
  const entered = useEntered();
  const [all, setAll] = useState(false);
  const sorted = [...skills].sort((a, b) => b.level - a.level || (b.years ?? 0) - (a.years ?? 0) || a.name_th.localeCompare(b.name_th, "th"));
  const shown = all ? sorted : sorted.slice(0, SHOW_SKILLS);
  return (
    <Tile
      title="ความแข็งแรงของทักษะด้านเทคนิค"
      icon={Sparkles}
      className="md:col-span-2 lg:col-span-3"
      action={
        sorted.length > SHOW_SKILLS && (
          <button type="button" onClick={() => setAll((v) => !v)} className="shrink-0 rounded-full border border-border px-3 py-1 text-tiny font-semibold text-text-muted hover:text-text">
            {all ? "แสดงน้อยลง" : `ดูทั้งหมด ${sorted.length}`}
          </button>
        )
      }
    >
      {shown.length ? (
        <ul className="space-y-3.5">
          {shown.map((s, i) => (
            <li key={s.skill_id} className="grid grid-cols-[minmax(0,15rem)_1fr_auto] items-center gap-x-5 text-small">
              <span className="truncate text-text" title={s.name_th}>
                {s.name_th}
              </span>
              <span className="flex h-4 gap-1" role="img" aria-label={`ระดับ ${s.level} ${levelLabel(s.level)}`}>
                {LEVELS.map((l) => (
                  <span
                    key={l.value}
                    className="flex-1 rounded-[3px] transition-[background-color] duration-500"
                    style={{
                      background: entered && s.level >= l.value ? "var(--color-series-1)" : "var(--color-border)",
                      transitionDelay: `${i * 40 + l.value * 60}ms`,
                    }}
                  />
                ))}
              </span>
              <span className="w-28 text-right text-tiny text-text-muted">
                <span className="font-semibold text-text">{levelLabel(s.level)}</span>
                {s.years ? ` · ${s.years} ปี` : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-small text-text-muted">ยังไม่มีทักษะด้านเทคนิค เพิ่มได้จาก CV แบบสอบถาม หรือแชท</p>
      )}
      <p className="mt-5 text-tiny text-text-muted">4 ช่อง = ระดับ 1 เริ่มต้น · 2 ใช้งานได้ · 3 คล่อง · 4 เชี่ยวชาญ</p>
    </Tile>
  );
}

/* ---------- skills per level ---------- */

/** Grouped columns: technical and teamwork skills at each level (two series, legend + direct counts). */
export function LevelMixTile({ hard, soft }) {
  const entered = useEntered();
  const count = (list, lv) => list.filter((s) => s.level === lv).length;
  const rows = LEVELS.map((l) => ({ ...l, hard: count(hard, l.value), soft: count(soft, l.value) }));
  const top = Math.max(1, ...rows.flatMap((r) => [r.hard, r.soft]));
  const series = [
    { key: "hard", label: "เทคนิค", color: "var(--color-series-1)" },
    { key: "soft", label: "ทำงานร่วมกับผู้อื่น", color: "var(--color-series-2)" },
  ];
  return (
    <Tile title="ทักษะในแต่ละระดับ" icon={BadgeCheck}>
      <ul className="mb-3 flex flex-wrap gap-x-3 gap-y-1">
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5 text-tiny text-text-muted">
            <span className="size-2.5 rounded-sm" style={{ background: s.color }} aria-hidden="true" />
            {s.label}
          </li>
        ))}
      </ul>
      <div className="mt-auto grid h-44 grid-cols-4 items-end gap-3 border-b border-border" role="img" aria-label={rows.map((r) => `ระดับ ${r.value}: เทคนิค ${r.hard} ทำงานร่วม ${r.soft}`).join(" · ")}>
        {rows.map((r, i) => (
          <div key={r.value} className="flex h-full items-end justify-center gap-0.5">
            {series.map((s) => (
              <span key={s.key} className="relative flex w-full max-w-5 flex-col items-center justify-end" style={{ height: "100%" }}>
                <span className="tabular mb-1 text-[11px] font-semibold text-text">{r[s.key] || ""}</span>
                <span
                  className="w-full rounded-t-[4px] transition-[height] duration-700 ease-out"
                  style={{ height: entered ? `${(r[s.key] / top) * 80}%` : "0%", background: s.color, transitionDelay: `${i * 80}ms` }}
                />
              </span>
            ))}
          </div>
        ))}
      </div>
      <div className="mt-1.5 grid grid-cols-4 gap-3">
        {rows.map((r) => (
          <p key={r.value} className="text-center text-[11px] leading-4 text-text-muted">
            {r.value}
            <br />
            {r.label}
          </p>
        ))}
      </div>
    </Tile>
  );
}

/* ---------- highlight ---------- */

export function StrengthCard({ profile }) {
  const top = strong(profile.hard_skills).sort((a, b) => b.level - a.level);
  const names = top.slice(0, 3).map((s) => s.name_th);
  const share = profile.hard_skills.length ? top.length / profile.hard_skills.length : 0;
  const blocks = Math.round(share * 10);
  return (
    <section aria-label="จุดแข็ง" className="bg-curtain relative isolate flex flex-col overflow-hidden rounded-2xl p-5 text-curtain-fg shadow-sm">
      <DotGrid intensity={0.45} clear={0.5} className="-z-10" />
      <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-tiny font-semibold">
        <Lightbulb className="size-3.5" strokeWidth={2} aria-hidden="true" />
        จุดแข็งของคุณ
      </span>
      <p className="mt-4 text-h3 leading-8 font-semibold">
        {names.length ? (
          <>
            เด่นที่ <span className="text-curtain-accent">{names.join(" · ")}</span>
            {top.length > names.length && ` และอีก ${top.length - names.length} ทักษะ`}
          </>
        ) : (
          "ยังไม่มีทักษะระดับคล่องขึ้นไป เติมระดับทักษะในแชทหรือแบบสอบถามได้"
        )}
      </p>
      <div className="mt-auto pt-5">
        <div className="flex gap-1" role="img" aria-label={`ทักษะระดับคล่องขึ้นไป ${pct(share)} ของทักษะด้านเทคนิค`}>
          {Array.from({ length: 10 }, (_, i) => (
            <span key={i} className={`h-3 flex-1 rounded ${i < blocks ? "bg-curtain-accent" : "bg-white/10"}`} />
          ))}
        </div>
        <p className="mt-2 text-tiny text-curtain-muted">ระดับคล่องขึ้นไป {pct(share)} ของทักษะด้านเทคนิค · คำนวณจากโปรไฟล์</p>
        <Link
          href="/roles"
          className="mt-4 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-full bg-curtain-accent px-4 text-small font-semibold text-[#0c1922] transition-transform duration-150 hover:-translate-y-0.5"
        >
          ดูสายงานที่เหมาะ
          <ArrowRight className="size-4" strokeWidth={2} aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}

/* ---------- traits, evidence, claims ---------- */

export function TraitsTile({ workStyle, values }) {
  return (
    <Tile title="ความชอบในการทำงาน" icon={Handshake} className="@container lg:col-span-2">
      <p className="-mt-2 mb-3 text-tiny text-text-muted">จากคำตอบที่คุณเลือกเอง · แตะแต่ละข้อเพื่อดูรายละเอียด</p>
      <WorkStyleTraits workStyle={workStyle} values={values} />
    </Tile>
  );
}

const EVIDENCE_KINDS = [
  { key: "cv_line", label: "CV", color: "var(--color-series-1)" },
  { key: "answer", label: "แบบสอบถาม", color: "var(--color-series-2)" },
  { key: "chat", label: "แชท", color: "var(--color-series-3)" },
  { key: "other", label: "อื่น ๆ", color: "var(--color-border)" },
];

/** Where the profile's claims come from: every evidence item cited by a skill or claim, by source. */
export function EvidenceTile({ profile }) {
  const ids = new Set([
    ...profile.hard_skills.flatMap((s) => s.evidence_ids),
    ...profile.soft_skills.flatMap((s) => s.evidence_ids),
    ...profile.experience.summary.flatMap((c) => c.evidence_ids),
    ...profile.blind_spots.flatMap((c) => c.evidence_ids),
    ...(profile.work_style.summary_evidence_ids ?? []),
  ]);
  const counts = {};
  for (const id of ids) {
    const kind = profile.evidence[id]?.kind;
    const k = ["cv_line", "answer", "chat"].includes(kind) ? kind : "other";
    counts[k] = (counts[k] ?? 0) + 1;
  }
  const total = ids.size || 1;
  const edited = [...profile.hard_skills, ...profile.soft_skills].filter((s) => s.edited_by_user).length;
  return (
    <Tile title="ที่มาของข้อมูล" icon={FileSearch}>
      <p className="tabular font-[family-name:var(--font-latin-first)] text-[36px] leading-none font-semibold text-text">
        {ids.size}
        <span className="ml-1.5 text-small font-medium text-text-muted">หลักฐาน</span>
      </p>
      <div className="mt-4">
        <ShareStrip
          label="ที่มาของหลักฐาน"
          items={EVIDENCE_KINDS.map((k) => ({ label: k.label, share: (counts[k.key] ?? 0) / total, color: k.color })).filter((i) => i.share > 0)}
        />
      </div>
      <p className="mt-auto pt-4 text-tiny text-text-muted">
        ทุกข้อมูลมีหลักฐานกำกับ [n] กดเพื่อดูที่มา{edited ? ` · คุณแก้ไขเอง ${edited} ทักษะ` : ""}
      </p>
    </Tile>
  );
}

export function BlindSpotsTile({ claims }) {
  return (
    <Tile title="สิ่งที่ยังควรสำรวจ" icon={Lightbulb} className="lg:col-span-2">
      <p className="-mt-2 mb-3 text-tiny text-text-muted">จุดที่ยังไม่มีหลักฐาน หรือที่คุณให้คะแนนตัวเองต่ำ</p>
      <ClaimList claims={claims} empty="ยังไม่พบจุดที่ควรสำรวจเพิ่ม" />
      <div className="mt-auto">
        <Disclaimer>ไม่ได้หมายความว่าคุณไม่มีทักษะนี้ เล่าเพิ่มในแชทเพื่อให้ภาพชัดขึ้นได้</Disclaimer>
      </div>
    </Tile>
  );
}

export function ExperienceTile({ experience }) {
  return (
    <Tile title="ประสบการณ์และการศึกษา" icon={Quote} className="md:col-span-2 lg:col-span-3">
      {monthsTh(experience.total_months) && <p className="-mt-2 mb-3 text-tiny text-text-muted">ประสบการณ์รวมประมาณ {monthsTh(experience.total_months)}</p>}
      <ClaimList claims={experience.summary} empty="ยังไม่มีข้อมูลประสบการณ์" />
    </Tile>
  );
}
