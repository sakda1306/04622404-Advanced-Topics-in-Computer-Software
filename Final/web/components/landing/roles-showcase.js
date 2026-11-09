"use client";

import { useEffect, useRef, useState } from "react";
import { BarChart3, Code2, Palette, ServerCog } from "lucide-react";
import { useReducedMotion } from "@/lib/use-motion";
import { Marquee } from "@/components/ui/marquee";

// Landing "สายงานที่รองรับ": a full-width band with a mint glow, a large count of the roles, one tile per role family, and
// a tilted wall of role cards in columns scrolling up and down (shuffled, each
// column in its own order). Picking a family tile highlights its roles in the
// wall. The count rises once when the panel comes into view; the wall pauses on
// hover. With reduced motion nothing moves.
// The band runs the full page width; it is pale in the light theme and dark in the
// dark theme (colours in globals.css, .roles-panel).

// Families are for this page only; the role files have no category field.
export const ROLE_FAMILIES = [
  {
    id: "dev",
    label: "พัฒนาซอฟต์แวร์",
    label_en: "Software Development",
    Icon: Code2,
    roles: [
      "software-engineer", "web-developer", "frontend-developer", "backend-developer", "fullstack-developer",
      "mobile-developer", "computer-engineer", "integration-engineer", "qa-engineer",
    ],
  },
  {
    id: "data",
    label: "ข้อมูลและ AI",
    label_en: "Data & AI",
    Icon: BarChart3,
    roles: [
      "data-analyst", "bi-analyst", "data-scientist", "data-engineer", "data-architect",
      "ml-engineer", "ai-engineer", "database-administrator",
    ],
  },
  {
    id: "infra",
    label: "โครงสร้างพื้นฐานและความปลอดภัย",
    label_en: "Infrastructure & Security",
    Icon: ServerCog,
    roles: ["devops-engineer", "cloud-engineer", "information-security-analyst", "network-administrator", "systems-administrator", "it-support"],
  },
  {
    id: "design",
    label: "ออกแบบและบริหาร",
    label_en: "Design & Management",
    Icon: Palette,
    roles: ["ux-ui-designer", "it-project-manager", "it-consultant"],
  },
];

const familyOf = Object.fromEntries(ROLE_FAMILIES.flatMap((f) => f.roles.map((r) => [r, f.id])));
const COUNT_MS = 1200;

/** Counts from 0 to `target` once, the first time `ref` is on screen. */
function useCountUp(target, ref) {
  const reduced = useReducedMotion();
  const [value, setValue] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    let frame = 0;
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        io.disconnect();
        const start = performance.now();
        const tick = (now) => {
          const t = Math.min(1, (now - start) / COUNT_MS);
          setValue(Math.round(target * (1 - Math.pow(1 - t, 3)))); // ease-out
          if (t < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [target, ref]);
  return reduced ? target : value;
}

const familyById = Object.fromEntries(ROLE_FAMILIES.map((f) => [f.id, f]));

// Seeded shuffle (mulberry32 + Fisher–Yates): the same order on the server and in
// the browser, so the page hydrates cleanly, but no column keeps the file order.
function shuffled(list, seed) {
  let t = seed >>> 0;
  const rand = () => {
    t += 0x6d2b79f5;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
  const out = [...list];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

const COLUMN_SEEDS = [11, 23, 37, 53];

function RoleCard({ role, family }) {
  const own = familyById[familyOf[role.role_id]];
  const { Icon } = own ?? ROLE_FAMILIES[0];
  const dim = family && own?.id !== family;
  const on = family && own?.id === family;
  return (
    <div
      className={`roles-chip flex w-60 items-center gap-3 rounded-xl px-3.5 py-3 text-left transition-[opacity,filter,box-shadow,transform] duration-300 ${
        dim ? "opacity-20 grayscale" : "opacity-100"
      } ${on ? "scale-105 shadow-lg ring-2 ring-[var(--roles-accent)]" : ""}`}
    >
      <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-[var(--roles-icon-bg)] text-[var(--roles-icon-fg)]">
        <Icon className="size-4.5" strokeWidth={1.75} />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-small font-semibold text-[var(--roles-fg)]">{role.title_th}</span>
        <span className="block truncate font-[family-name:var(--font-latin-first)] text-tiny text-[var(--roles-muted)]" lang="en">
          {role.title_en}
        </span>
      </span>
    </div>
  );
}

// The wall is decorative motion; screen readers get the plain list below it.
function RoleWall({ roles, family }) {
  const columns = COLUMN_SEEDS.map((seed) => shuffled(roles, seed));
  return (
    <>
      <div className="roles-wall relative mx-auto h-[26rem] w-full max-w-[1120px] overflow-hidden [perspective:300px] md:h-[30rem]" aria-hidden="true">
        <div
          className="absolute top-1/2 left-1/2 flex flex-row items-center gap-4"
          style={{ transform: "translate(-50%, -50%) translateX(-60px) translateZ(-100px) rotateX(20deg) rotateY(-10deg) rotateZ(20deg)" }}
        >
          {columns.map((list, i) => (
            <Marquee key={COLUMN_SEEDS[i]} vertical pauseOnHover reverse={i % 2 === 1} repeat={2} aria-hidden="true" className="h-[60rem] [--duration:50s]">
              {list.map((r) => (
                <RoleCard key={r.role_id} role={r} family={family} />
              ))}
            </Marquee>
          ))}
        </div>
      </div>
      <ul className="sr-only">
        {roles.map((r) => (
          <li key={r.role_id}>
            {r.title_th} ({r.title_en})
          </li>
        ))}
      </ul>
    </>
  );
}

function FamilyTile({ family, on, onToggle }) {
  const { label, label_en, Icon, roles } = family;
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onToggle}
      className={`roles-tile group relative flex items-center gap-4 rounded-xl px-5 py-4 text-left transition-[background-color,border-color,transform] duration-200 ease-out hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--roles-accent)] ${
        on ? "roles-tile-on" : ""
      }`}
    >
      {/* icon square with faint crosshair lines, as in the reference */}
      <span className="relative shrink-0" aria-hidden="true">
        <span className="roles-crosshair absolute top-1/2 -right-3 -left-3 h-px -translate-y-1/2" />
        <span className="roles-crosshair absolute -top-3 -bottom-3 left-1/2 w-px -translate-x-1/2" />
        <span className="relative inline-flex size-12 items-center justify-center rounded-lg bg-[var(--roles-icon-bg)] text-[var(--roles-icon-fg)] shadow-sm">
          <Icon className="size-6" strokeWidth={1.5} />
        </span>
      </span>
      <span className="min-w-0">
        <span className="block font-[family-name:var(--font-latin-first)] text-[28px] leading-8 font-semibold text-[var(--roles-fg)] tabular">
          {roles.length}
        </span>
        <span className="mt-0.5 block text-small text-[var(--roles-fg)]">{label}</span>
        <span className="block font-[family-name:var(--font-latin-first)] text-tiny text-[var(--roles-muted)]" lang="en">
          {label_en}
        </span>
      </span>
    </button>
  );
}

export function RolesShowcase({ roles }) {
  const [family, setFamily] = useState(null);
  const numberRef = useRef(null);
  const count = useCountUp(roles.length, numberRef);
  const stages = roles.reduce((acc, r) => ({ ...acc, [r.career_stage]: (acc[r.career_stage] ?? 0) + 1 }), {});
  const experienced = (stages.mid ?? 0) + (stages.senior ?? 0);

  return (
    <div className="roles-panel relative isolate overflow-hidden pt-16 pb-10 text-center md:pt-20">
      <div className="mx-auto max-w-[1120px] px-4 md:px-6">
      <h2 className="mx-auto max-w-3xl text-h1 font-bold text-[var(--roles-fg)] md:text-[44px] md:leading-[60px]">
        สายงานที่ระบบเทียบให้คุณ
      </h2>
      <p className="mx-auto mt-4 max-w-2xl text-body text-[var(--roles-muted)]">
        แต่ละสายงานมีรายการทักษะ ระดับที่ต้องการ และแหล่งอ้างอิง ระบบนำโปรไฟล์ของคุณไปเทียบกับทุกสายงาน แล้วเรียงสายงานที่ใกล้เคียงที่สุดให้
      </p>

      <div ref={numberRef} className="mt-10 md:mt-12">
        <p
          className="inline-block px-2 font-[family-name:var(--font-latin-first)] text-[var(--roles-fg)] text-[128px] leading-none font-bold tracking-tight tabular md:text-[220px]"
          aria-hidden="true"
        >
          {count}
        </p>
        <p className="mt-2 text-h3 font-semibold text-[var(--roles-fg)] md:text-[24px]">
          <span className="sr-only">{roles.length} </span>สายงาน IT ที่เทียบได้
        </p>
        <p className="mt-2 text-small text-[var(--roles-muted)]">
          ตำแหน่งเริ่มต้น {stages.entry ?? 0} สายงาน · ต้องมีประสบการณ์ก่อน {experienced} สายงาน
        </p>
      </div>

      <p id="family-label" className="sr-only">
        กลุ่มสายงาน เลือกเพื่อดูสายงานในกลุ่ม
      </p>
      <div role="group" aria-labelledby="family-label" className="mx-auto mt-12 grid max-w-[980px] gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {ROLE_FAMILIES.map((f) => (
          <FamilyTile key={f.id} family={f} on={family === f.id} onToggle={() => setFamily(family === f.id ? null : f.id)} />
        ))}
      </div>
      <p className="mt-4 text-tiny text-[var(--roles-muted)]">เลือกกลุ่มเพื่อดูสายงานในกลุ่มนั้น</p>
      </div>

      <div className="mt-6" role="region" aria-label="รายชื่อสายงานที่รองรับ">
        <RoleWall roles={roles} family={family} />
      </div>
    </div>
  );
}
