"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import Image from "next/image";
import { cn } from "@/lib/utils";

export type TravelTestimonial = {
  text: string;
  image: string;
  name: string;
  role: string;
};

export function TestimonialsColumn({
  className,
  testimonials,
  duration = 16,
}: {
  className?: string;
  testimonials: TravelTestimonial[];
  duration?: number;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <div className={cn("w-full max-w-xs overflow-hidden", className)}>
      <motion.div
        animate={reduceMotion ? undefined : { translateY: "-50%" }}
        transition={{
          duration,
          repeat: Infinity,
          ease: "linear",
          repeatType: "loop",
        }}
        className="flex flex-col gap-5 pb-5"
      >
        {[0, 1].map((set) => (
          <React.Fragment key={set}>
            {testimonials.map((item, index) => (
              <article
                key={`${set}-${index}`}
                className="rounded-2xl border border-[#bdd9e9] bg-white p-6 shadow-[0_12px_30px_rgba(7,29,53,.08)]"
              >
                <span className="font-display text-4xl leading-none text-aqua">
                  “
                </span>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {item.text}
                </p>
                <div className="mt-5 flex items-center gap-3">
                  <Image
                    src={item.image}
                    alt={item.name}
                    width={40}
                    height={40}
                    className="h-10 w-10 rounded-full object-cover ring-2 ring-[#e8f4fb]"
                  />
                  <div>
                    <b className="block text-sm text-ink">{item.name}</b>
                    <span className="text-xs text-slate-500">{item.role}</span>
                  </div>
                </div>
              </article>
            ))}
          </React.Fragment>
        ))}
      </motion.div>
    </div>
  );
}

const testimonials: TravelTestimonial[] = [
  {
    text: "คำเตือนเรื่องหมอกทำให้เราเปลี่ยนเวลาออกเดินทาง — แล้วได้วิวที่ดีกว่าเดิมด้วย",
    image:
      "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=160&q=80",
    name: "Mali, Bangkok",
    role: "Mae Hong Son loop",
  },
  {
    text: "ชอบที่ระบบบอกเหตุผล ไม่ได้บอกแค่ว่าปลอดภัยหรือไม่ปลอดภัย",
    image:
      "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=160&q=80",
    name: "Niran & family",
    role: "Phuket to Krabi",
  },
  {
    text: "เรียบง่ายพอให้ใช้จริงก่อนออกจากบ้าน แต่ข้อมูลลึกพอเมื่ออยากรู้เพิ่ม",
    image:
      "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=160&q=80",
    name: "Anya, Chiang Mai",
    role: "Weekend by the sea",
  },
  {
    text: "มันทำให้การเลือกเลื่อนทริปเป็นการตัดสินใจที่มั่นใจขึ้นมาก",
    image:
      "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=160&q=80",
    name: "Than, Rayong",
    role: "Coastal road trip",
  },
  {
    text: "ข้อมูลแจ้งเตือนเข้าใจง่าย และทำให้เราวางแผนจุดแวะได้พอดี",
    image:
      "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=160&q=80",
    name: "Pim, Nonthaburi",
    role: "Family weekend",
  },
  {
    text: "เรายังได้ไปถึงทะเลเหมือนเดิม แต่ไปในเวลาที่ปลอดภัยกว่า",
    image:
      "https://images.unsplash.com/photo-1519345182560-3f2917c472ef?auto=format&fit=crop&w=160&q=80",
    name: "Krit, Bangkok",
    role: "Andaman escape",
  },
];

export function CoastalTestimonials() {
  return (
    <section className="bg-white px-6 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl">
        <div className="text-center">
          <p className="text-xs font-bold tracking-[.2em] text-aqua">
            MOMENTS, NOT MISSED
          </p>
          <h2 className="mt-4 font-display text-5xl text-ink sm:text-6xl">
            Stories that keep moving.
          </h2>
          <p className="mx-auto mt-5 max-w-lg text-sm leading-6 text-slate-600">
            เรื่องเล่าจริงที่เคลื่อนผ่านไปอย่างนุ่มนวล
            เหมือนการเดินทางที่ได้รับการเตรียมพร้อม
          </p>
        </div>
        <div className="mt-12 flex max-h-[580px] justify-center gap-5 overflow-hidden [mask-image:linear-gradient(to_bottom,transparent,black_12%,black_88%,transparent)]">
          <TestimonialsColumn
            testimonials={testimonials.slice(0, 2)}
            duration={15}
          />
          <TestimonialsColumn
            testimonials={testimonials.slice(2, 4)}
            duration={19}
            className="hidden md:block"
          />
          <TestimonialsColumn
            testimonials={testimonials.slice(4, 6)}
            duration={17}
            className="hidden lg:block"
          />
        </div>
      </div>
    </section>
  );
}
