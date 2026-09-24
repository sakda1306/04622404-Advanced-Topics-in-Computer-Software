"use client";

import { motion, useReducedMotion } from "motion/react";
import { ArrowUpRight, Compass } from "lucide-react";

/** A scroll-triggered door opening that reveals the coast without locking page scroll. */
export function CoastalDoorReveal() {
  const reduceMotion = useReducedMotion();
  const leftDoor = { closed: { x: 0, rotateY: 0 }, open: reduceMotion ? { x: "-14%" } : { x: "-58%", rotateY: -26 } };
  const rightDoor = { closed: { x: 0, rotateY: 0 }, open: reduceMotion ? { x: "14%" } : { x: "58%", rotateY: 26 } };
  return <section className="bg-[#eaf5fb] px-6 py-24 sm:py-32">
    <div className="mx-auto max-w-7xl">
      <div className="mb-10 flex flex-col justify-between gap-5 md:flex-row md:items-end">
        <div><p className="text-xs font-bold tracking-[.2em] text-aqua">OPEN TO WHAT&apos;S AHEAD</p><h2 className="mt-4 font-display text-5xl leading-none text-ink sm:text-6xl">A clearer view<br/>begins here.</h2></div>
        <p className="max-w-sm text-sm leading-6 text-slate-600">เปิดดูเส้นทางที่เป็นไปได้ก่อนออกเดินทาง แล้วเลือกแผนที่เหมาะกับจังหวะของคุณ</p>
      </div>
      <motion.div initial={{ opacity: 0, y: 28 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.35 }} transition={{ duration: reduceMotion ? 0 : 0.65 }}>
        <motion.div initial="closed" animate="closed" whileHover="open" className="group relative h-[440px] overflow-hidden rounded-[2rem] bg-[#071d35] shadow-float sm:h-[540px]">
          <div className="absolute inset-0 bg-cover" style={{ backgroundImage: "url('/door-traveler.png')", backgroundPosition: "center 76%" }} />
          <div className="absolute inset-0 bg-gradient-to-t from-[#03162c]/70 via-[#03162c]/5 to-transparent" />
          <div className="absolute inset-x-0 bottom-0 z-10 flex flex-col justify-between gap-6 p-7 text-white sm:flex-row sm:items-end sm:p-10"><div><span className="flex items-center gap-2 text-xs font-bold tracking-[.18em] text-[#b9e5fb]"><Compass size={15}/> COASTAL ROUTE PREVIEW</span><h3 className="mt-3 font-display text-4xl sm:text-5xl">Let the horizon<br/>open slowly.</h3></div><button className="flex items-center gap-2 rounded-full bg-white px-5 py-3 text-xs font-bold text-ink">EXPLORE THE ROUTE <ArrowUpRight size={15}/></button></div>
          <span className="pointer-events-none absolute left-1/2 top-7 z-[3] -translate-x-1/2 rounded-full border border-white/25 bg-[#071d35]/55 px-3 py-1.5 text-[10px] font-bold tracking-[.16em] text-white backdrop-blur transition-opacity duration-300 group-hover:opacity-0">HOVER TO OPEN</span>
          <motion.div aria-hidden variants={leftDoor} transition={{ duration: reduceMotion ? 0 : .8, ease: [0.16, 1, 0.3, 1] }} className="absolute inset-y-0 left-0 z-[2] w-1/2 origin-left border-r border-white/15 bg-gradient-to-br from-[#153e62] via-[#0c2948] to-[#061a31] shadow-2xl"><span className="absolute right-6 top-1/2 h-11 w-1 rounded-full bg-[#b9e5fb]/80 shadow-[0_0_18px_rgba(185,229,251,.7)]" /></motion.div>
          <motion.div aria-hidden variants={rightDoor} transition={{ duration: reduceMotion ? 0 : .8, ease: [0.16, 1, 0.3, 1] }} className="absolute inset-y-0 right-0 z-[2] w-1/2 origin-right border-l border-white/15 bg-gradient-to-bl from-[#153e62] via-[#0c2948] to-[#061a31] shadow-2xl"><span className="absolute left-6 top-1/2 h-11 w-1 rounded-full bg-[#b9e5fb]/80 shadow-[0_0_18px_rgba(185,229,251,.7)]" /></motion.div>
        </motion.div>
      </motion.div>
    </div>
  </section>;
}
