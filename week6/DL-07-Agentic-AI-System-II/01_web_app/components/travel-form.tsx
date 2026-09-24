"use client";
import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  ArrowUpRight,
  CalendarDays,
  ChevronDown,
  Clock,
  LoaderCircle,
  MapPin,
  Navigation,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useTrip } from "@/components/trip-context";
import type { AvoidOption } from "@/lib/types";

const schema = z.object({
  origin: z.string().min(2, "ระบุจุดเริ่มต้นอย่างน้อย 2 ตัวอักษร"),
  destination: z.string().min(2, "ระบุปลายทางอย่างน้อย 2 ตัวอักษร"),
  date: z.string().min(1, "เลือกวันเดินทาง"),
  time: z.string().default("08:00"),
  mode: z.enum(["CAR", "BUS", "TRAIN", "FLIGHT", "FERRY", "WALK", "BICYCLE"]),
  travelerCount: z.coerce.number().min(1).max(20).default(1),
  avoidHighways: z.boolean().default(false),
  avoidTolls: z.boolean().default(false),
  avoidFerries: z.boolean().default(false),
  avoidNight: z.boolean().default(false),
  note: z.string().max(240).optional(),
}).superRefine(({ date, time, avoidNight }, ctx) => {
  if (new Date(`${date}T${time}:00+07:00`).getTime() <= Date.now()) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["date"], message: "เลือกวันและเวลาเดินทางในอนาคต" });
  }
  const hour = Number(time.split(":")[0]);
  if (avoidNight && (hour < 6 || hour >= 18)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["time"],
      message: "เปิดการเลี่ยงกลางคืนแล้ว กรุณาเลือกเวลา 06:00–17:59 น.",
    });
  }
});
type Form = z.infer<typeof schema>;

function bangkokDate(daysFromNow: number): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Bangkok",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(Date.now() + daysFromNow * 86_400_000));
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

const BUSY_STATUS = new Set(["geocoding", "submitting", "streaming"]);
const STATUS_LABEL: Record<string, string> = {
  geocoding: "กำลังค้นหาตำแหน่งบนแผนที่…",
  submitting: "กำลังส่งคำขอไปยังเซิร์ฟเวอร์…",
  streaming: "กำลังประเมินความเสี่ยง…",
};

export function TravelForm() {
  const {
    status,
    submit,
    recommendation,
    usingMock,
    originPoint,
    destinationPoint,
    lastInput,
    pinningMode,
    setPinningMode,
  } = useTrip();
  const [showPreferences, setShowPreferences] = useState(false);
  const [minDate, setMinDate] = useState("");
  const busy = BUSY_STATUS.has(status);

  const form = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: {
      origin: "Bangkok",
      destination: "Chiang Mai",
      date: "",
      time: "08:00",
      mode: "CAR",
      travelerCount: 1,
      avoidHighways: false,
      avoidTolls: false,
      avoidFerries: false,
      avoidNight: false,
      note: "",
    },
  });

  useEffect(() => {
    setMinDate(bangkokDate(0));
    if (!lastInput?.date) form.setValue("date", bangkokDate(1));
  }, [form, lastInput?.date]);

  useEffect(() => {
    if (lastInput) {
      if (lastInput.origin) form.setValue("origin", lastInput.origin, { shouldValidate: true });
      if (lastInput.destination) form.setValue("destination", lastInput.destination, { shouldValidate: true });
      if (lastInput.date) form.setValue("date", lastInput.date, { shouldValidate: true });
      if (lastInput.time) form.setValue("time", lastInput.time, { shouldValidate: true });
      if (lastInput.mode) form.setValue("mode", lastInput.mode, { shouldValidate: true });
    }
  }, [lastInput, form]);

  useEffect(() => {
    if (originPoint?.name) {
      form.setValue("origin", originPoint.name, { shouldValidate: true });
    }
  }, [originPoint, form]);

  useEffect(() => {
    if (destinationPoint?.name) {
      form.setValue("destination", destinationPoint.name, { shouldValidate: true });
    }
  }, [destinationPoint, form]);

  const onSubmit = (data: Form) => {
    const avoid: AvoidOption[] = [];
    if (data.avoidHighways) avoid.push("HIGHWAYS");
    if (data.avoidTolls) avoid.push("TOLLS");
    if (data.avoidFerries) avoid.push("FERRIES");
    if (data.avoidNight) avoid.push("NIGHT_TRAVEL");

    return submit({
      origin: data.origin,
      destination: data.destination,
      date: data.date,
      time: data.time,
      mode: data.mode,
      avoid,
      travelerCount: data.travelerCount,
      note: data.note,
    });
  };

  return (
    <form
      onSubmit={form.handleSubmit(onSubmit)}
      className="grid gap-3 text-left md:grid-cols-2"
    >
      <Field
        icon={<Navigation size={16} />}
        label="จุดเริ่มต้น"
        error={form.formState.errors.origin?.message}
        action={
          <button
            type="button"
            onClick={() => setPinningMode(pinningMode === "origin" ? null : "origin")}
            style={{ minHeight: 44 }}
            className={`inline-flex items-center gap-1 rounded px-3 text-xs font-semibold transition ${
              pinningMode === "origin"
                ? "bg-aqua text-white shadow-xs"
                : "text-aqua hover:bg-aqua/10"
            }`}
          >
            <MapPin size={11} /> ปักหมุด
          </button>
        }
      >
        <input aria-label="Origin" {...form.register("origin")} />
      </Field>
      <Field
        icon={<MapPin size={16} />}
        label="ปลายทาง"
        error={form.formState.errors.destination?.message}
        action={
          <button
            type="button"
            onClick={() => setPinningMode(pinningMode === "destination" ? null : "destination")}
            style={{ minHeight: 44 }}
            className={`inline-flex items-center gap-1 rounded px-3 text-xs font-semibold transition ${
              pinningMode === "destination"
                ? "bg-amber-600 text-white shadow-xs"
                : "text-amber-600 hover:bg-amber-500/10"
            }`}
          >
            <MapPin size={11} /> ปักหมุด
          </button>
        }
      >
        <input aria-label="Destination" {...form.register("destination")} />
      </Field>
      <Field icon={<CalendarDays size={16} />} label="ออกเดินทาง">
        <input aria-label="Departure date" type="date" min={minDate} {...form.register("date")} />
      </Field>
      <Field icon={<Navigation size={16} />} label="การเดินทาง">
        <select aria-label="Travel mode" {...form.register("mode")}>
          <option value="CAR">ขับรถ (Car)</option>
          <option value="BUS">รถโดยสารประจำทาง (Bus)</option>
          <option value="TRAIN">รถไฟ (Train)</option>
          <option value="FLIGHT">เครื่องบิน (Flight)</option>
          <option value="FERRY">เรือ (Ferry)</option>
          <option value="WALK">เดินเท้า (Walk)</option>
          <option value="BICYCLE">จักรยาน (Bicycle)</option>
        </select>
      </Field>

      <div className="md:col-span-2">
        <button
          type="button"
          onClick={() => setShowPreferences((prev) => !prev)}
          className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-slate-50/70 px-3.5 py-2.5 text-xs font-bold text-pine transition hover:bg-slate-100"
        >
          <span className="flex items-center gap-1.5">
            <SlidersHorizontal size={14} className="text-aqua" />
            ตัวเลือกการเดินทางเพิ่มเติม (Travel Preferences)
          </span>
          <ChevronDown
            size={16}
            className={`transition duration-200 ${showPreferences ? "rotate-180 text-aqua" : "text-slate-400"}`}
          />
        </button>

        {showPreferences && (
          <div className="mt-2.5 space-y-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
            <div className="grid grid-cols-2 gap-3">
              <Field icon={<Clock size={15} />} label="เวลาออกเดินทาง" error={form.formState.errors.time?.message}>
                <input aria-label="Departure time" type="time" {...form.register("time")} />
              </Field>
              <Field icon={<Users size={15} />} label="จำนวนผู้เดินทาง">
                <input
                  aria-label="Traveler count"
                  type="number"
                  min={1}
                  max={20}
                  {...form.register("travelerCount")}
                />
              </Field>
            </div>

            <div>
              <span className="mb-1.5 block text-xs font-bold text-slate-500">
                ตัวเลือกหลีกเลี่ยง (Avoid Options)
              </span>
              <div className="grid grid-cols-2 gap-2 text-xs text-slate-700 sm:grid-cols-4">
                <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 p-2 hover:bg-slate-100">
                  <input type="checkbox" {...form.register("avoidHighways")} className="rounded text-aqua" />
                  <span>เลี่ยงทางด่วน</span>
                </label>
                <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 p-2 hover:bg-slate-100">
                  <input type="checkbox" {...form.register("avoidTolls")} className="rounded text-aqua" />
                  <span>เลี่ยงค่าผ่านทาง</span>
                </label>
                <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 p-2 hover:bg-slate-100">
                  <input type="checkbox" {...form.register("avoidFerries")} className="rounded text-aqua" />
                  <span>เลี่ยงเรือข้ามฟาก</span>
                </label>
                <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 p-2 hover:bg-slate-100">
                  <input type="checkbox" {...form.register("avoidNight")} className="rounded text-aqua" />
                  <span>เลี่ยงกลางคืน</span>
                </label>
              </div>
            </div>
          </div>
        )}
      </div>

      <label className="md:col-span-2">
        <span className="mb-1 block text-xs font-bold tracking-wider text-slate-500">บอกเราเพิ่มเติม (ไม่บังคับ)</span>
        <input
          className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none focus:border-aqua"
          placeholder="เช่น มีผู้สูงอายุร่วมเดินทาง อยากเลี่ยงถนนเขา"
          {...form.register("note")}
        />
      </label>

      {status === "success" && recommendation && (
        <p role="status" className="md:col-span-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
          ประเมินเสร็จแล้ว{usingMock ? " (ข้อมูลตัวอย่าง)" : ""} — เลื่อนลงไปดูผลที่{" "}
          <a href="#dashboard" className="font-bold underline underline-offset-2">
            แดชบอร์ดคำแนะนำ
          </a>
        </p>
      )}
      {status === "error" && (
        <p role="alert" className="md:col-span-2 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          ไม่สามารถประเมินเส้นทางได้ในขณะนี้ ลองใหม่อีกครั้ง
        </p>
      )}

      <button
        className="md:col-span-2 flex items-center justify-center gap-2 rounded-full bg-ink px-5 py-4 text-sm font-bold text-white transition hover:bg-pine disabled:opacity-60"
        disabled={busy}
      >
        {busy ? (
          <>
            <LoaderCircle className="animate-spin" size={18} /> {STATUS_LABEL[status]}
          </>
        ) : (
          <>
            ตรวจเส้นทางอย่างมั่นใจ <ArrowUpRight size={18} />
          </>
        )}
      </button>
    </form>
  );
}

function Field({
  icon,
  label,
  error,
  action,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  error?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <span className="mb-1 flex items-center justify-between gap-1.5 text-xs font-bold tracking-wider text-slate-500">
        <span className="flex items-center gap-1.5">
          {icon}
          {label}
        </span>
        {action}
      </span>
      <div className="[&_input]:w-full [&_input]:rounded-xl [&_input]:border [&_input]:border-slate-200 [&_input]:bg-slate-50 [&_input]:px-4 [&_input]:py-3 [&_input]:text-sm [&_input]:outline-none [&_input]:focus:border-aqua [&_select]:w-full [&_select]:rounded-xl [&_select]:border [&_select]:border-slate-200 [&_select]:bg-slate-50 [&_select]:px-4 [&_select]:py-3 [&_select]:text-sm">
        {children}
      </div>
      {error && <span className="mt-1 block text-xs text-red-700">{error}</span>}
    </div>
  );
}
