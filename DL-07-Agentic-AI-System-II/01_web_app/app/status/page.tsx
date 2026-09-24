"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  RefreshCw,
  XCircle,
} from "lucide-react";
import {
  fetchServiceStatus,
  type ComponentState,
  type ServiceComponent,
} from "@/lib/api/service-status";

// Icon + words carry the meaning; colour only reinforces it (WCAG 2.1 AA).
const STATE_UI: Record<
  ComponentState,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  operational: {
    label: "ใช้งานได้ปกติ",
    icon: CheckCircle2,
    className: "text-emerald-700",
  },
  degraded: {
    label: "ทำงานได้บางส่วน",
    icon: AlertTriangle,
    className: "text-amber-700",
  },
  down: { label: "ใช้งานไม่ได้", icon: XCircle, className: "text-red-700" },
  unknown: {
    label: "ไม่ทราบสถานะ",
    icon: CircleHelp,
    className: "text-slate-500",
  },
};

export default function StatusPage() {
  const { data, error, isPending, isFetching, refetch, dataUpdatedAt } =
    useQuery({
      queryKey: ["service-status"],
      queryFn: ({ signal }) => fetchServiceStatus(signal),
      refetchInterval: 60_000,
    });

  return (
    <main className="mx-auto w-full max-w-2xl px-5 py-10">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">สถานะระบบ</h1>
          <p className="mt-1 text-sm text-slate-600">
            ความพร้อมของบริการที่ใช้ประเมินความปลอดภัยการเดินทาง
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
        >
          <RefreshCw
            className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
            aria-hidden
          />
          ตรวจสอบใหม่
        </button>
      </header>

      <div className="mt-8" aria-live="polite">
        {isPending && <p className="text-sm text-slate-600">กำลังตรวจสอบ…</p>}

        {error && (
          <div className="rounded-md border border-red-300 bg-red-50 p-4">
            <p className="flex items-center gap-2 font-medium text-red-800">
              <XCircle className="h-5 w-5" aria-hidden />
              ตรวจสอบสถานะไม่สำเร็จ
            </p>
            <p className="mt-1 text-sm text-red-800">
              ไม่สามารถเชื่อมต่อบริการตรวจสอบสถานะได้ กรุณาลองใหม่ในภายหลัง
            </p>
          </div>
        )}

        {data && (
          <>
            <OverallBanner state={data.overall} />
            <ul className="mt-6 divide-y divide-slate-200 border-y border-slate-200">
              {data.components.map((component) => (
                <ComponentRow key={component.key} component={component} />
              ))}
            </ul>
            {data.components.length === 0 && (
              <p className="mt-6 text-sm text-slate-600">
                ระบบไม่ได้ส่งรายการบริการกลับมา ดูข้อมูลดิบด้านล่าง
              </p>
            )}
            <p className="mt-4 text-xs text-slate-500">
              ข้อมูลล่าสุด {new Date(dataUpdatedAt).toLocaleTimeString("th-TH")}{" "}
              · ตรวจสอบอัตโนมัติทุก 1 นาที
            </p>

            {/* Remove once the response shape is locked with the backend team. */}
            <details className="mt-6">
              <summary className="cursor-pointer text-sm text-slate-600">
                ข้อมูลดิบจาก API
              </summary>
              <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
                {JSON.stringify(data.raw, null, 2)}
              </pre>
            </details>
          </>
        )}
      </div>
    </main>
  );
}

function OverallBanner({ state }: { state: ComponentState }) {
  const { label, icon: Icon, className } = STATE_UI[state];
  const headline =
    state === "operational"
      ? "ทุกบริการพร้อมใช้งาน"
      : state === "degraded"
        ? "บางบริการทำงานได้ไม่เต็มที่"
        : state === "down"
          ? "มีบริการที่ใช้งานไม่ได้"
          : "ยังไม่ทราบสถานะระบบ";

  return (
    <div className="flex items-center gap-3 rounded-md bg-slate-50 p-4">
      <Icon className={`h-6 w-6 shrink-0 ${className}`} aria-hidden />
      <div>
        <p className="font-medium text-slate-900">{headline}</p>
        <p className="text-sm text-slate-600">{label}</p>
      </div>
    </div>
  );
}

function ComponentRow({ component }: { component: ServiceComponent }) {
  const { label, icon: Icon, className } = STATE_UI[component.state];

  return (
    <li className="flex items-start justify-between gap-4 py-3">
      <div>
        <p className="font-medium text-slate-900">{component.label}</p>
        {component.message && (
          <p className="mt-0.5 text-sm text-slate-600">{component.message}</p>
        )}
        {component.checkedAt && (
          <p className="mt-0.5 text-xs text-slate-500">
            อัปเดต {new Date(component.checkedAt).toLocaleString("th-TH")}
          </p>
        )}
      </div>
      <span
        className={`flex shrink-0 items-center gap-1.5 text-sm ${className}`}
      >
        <Icon className="h-4 w-4" aria-hidden />
        {label}
      </span>
    </li>
  );
}
