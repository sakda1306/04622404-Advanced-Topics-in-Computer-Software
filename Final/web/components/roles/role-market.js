"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CalendarCheck, ExternalLink, Info, Loader2, MapPin } from "lucide-react";
import { data } from "@/lib/data";
import { baht, bahtRange, dateTh, num } from "@/lib/format";
import { SalaryRange } from "@/components/charts/salary-range";
import { TrendingSkills } from "@/components/charts/match";
import { Card, ErrorState, LoadingBlock } from "@/components/intake/ui";

// Salary, market demand and listings for one role (FR-21, FR-22, FR-22b – f),
// always read from the shared cache. Every figure shows its source, measure and
// date; sections are labelled "ข้อมูลกรุงเทพฯ". While a scheduled refresh of this
// role runs (`refreshing`), the page polls every 5 s.

const POLL_MS = 5000;
const MEASURE_TH = { monthly_base: "/ เดือน (ฐานเงินเดือน)", annual_total: "/ ปี (รวมทุกอย่าง)" };
const LAYER_TH = { advertised: "ที่ประกาศในงาน", curated_reference: "ตารางอ้างอิงของทีม", official_baseline: "ค่าจ้างอุตสาหกรรม IT" };

export function BangkokLabel() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary-subtle px-2.5 py-0.5 text-tiny font-medium text-text">
      <MapPin className="size-3.5" strokeWidth={2} aria-hidden="true" />
      ข้อมูลกรุงเทพฯ
    </span>
  );
}

/** Data freshness badge (DesignSystem.md section 3): fresh, stale, refreshing, unavailable. */
export function FreshnessBadge({ market }) {
  if (market.refreshing) {
    return (
      <span role="status" className="inline-flex items-center gap-1.5 text-tiny text-text-muted">
        <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" strokeWidth={2} aria-hidden="true" />
        กำลังอัปเดตข้อมูล
      </span>
    );
  }
  if (!market.available || !market.fetched_at) return null;
  if (market.stale) {
    return (
      <span className="inline-flex items-center gap-1.5 text-tiny font-medium text-warning">
        <AlertTriangle className="size-3.5" strokeWidth={2} aria-hidden="true" />
        ข้อมูลอาจไม่เป็นปัจจุบัน · อัปเดตล่าสุด {dateTh(market.fetched_at)}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-tiny text-text-muted">
      <CalendarCheck className="size-3.5" strokeWidth={2} aria-hidden="true" />
      อัปเดตล่าสุด {dateTh(market.fetched_at)}
    </span>
  );
}

function SalaryRow({ range }) {
  const single = range.min_thb === range.max_thb;
  return (
    <li className="py-3">
      <p className="text-tiny font-semibold text-text-muted">{LAYER_TH[range.source_type]}</p>
      <p className="tabular mt-0.5 text-body font-semibold text-text">
        {single ? baht(range.min_thb) : bahtRange(range.min_thb, range.max_thb)}{" "}
        <span className="text-small font-normal text-text-muted">{MEASURE_TH[range.measure]}</span>
      </p>
      <p className="mt-0.5 text-tiny text-text-muted">
        แหล่งที่มา:{" "}
        {range.url ? (
          <a href={range.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
            {range.source}
          </a>
        ) : (
          range.source
        )}
        {" · "}ข้อมูล ณ {dateTh(range.as_of)}
        {range.sample_size ? ` · จาก ${num(range.sample_size)} ประกาศที่ระบุเงินเดือน` : ""}
        {single ? " · ตัวเลขเดียวตามอุตสาหกรรม ไม่ใช่ช่วงของสายงานนี้" : ""}
      </p>
    </li>
  );
}

function toLayers(salary) {
  const layers = [];
  if (salary.advertised) layers.push({ key: "advertised", label: LAYER_TH.advertised, min: salary.advertised.min_thb, max: salary.advertised.max_thb, source: salary.advertised.source, detail: `จาก ${salary.advertised.sample_size ?? "-"} ประกาศ`, asOf: salary.advertised.as_of });
  if (salary.reference) layers.push({ key: "reference", label: LAYER_TH.curated_reference, min: salary.reference.min_thb, max: salary.reference.max_thb, source: salary.reference.source, detail: "เงินเดือนเริ่มต้น", asOf: salary.reference.as_of });
  if (salary.baseline) layers.push({ key: "baseline", label: LAYER_TH.official_baseline, value: salary.baseline.min_thb, source: salary.baseline.source, detail: "ตัวเลขเดียวตามอุตสาหกรรม", asOf: salary.baseline.as_of });
  return layers;
}

/** `owned` (optional): Set of the user's skill_ids, marked in the in-demand skills chart. */
export function RoleMarket({ roleId, roleTitle, owned }) {
  const [market, setMarket] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(
    () =>
      data.roleMarket(roleId, { listings: 5 }).then(
        (m) => {
          setError(null);
          setMarket(m);
        },
        (e) => setError(e),
      ),
    [roleId],
  );

  useEffect(() => {
    load();
  }, [load]);

  // Poll while a scheduled refresh of this role is running (Contract.md 2.7).
  useEffect(() => {
    if (!market?.refreshing) return;
    const t = setTimeout(load, POLL_MS);
    return () => clearTimeout(t);
  }, [market, load]);

  if (error) return <ErrorState error={error} onRetry={load} />;
  if (!market) return <LoadingBlock lines={4} label="กำลังโหลดข้อมูลตลาดงาน…" />;

  const head = (title) => (
    <span className="flex flex-wrap items-center gap-2">
      {title}
      <BangkokLabel />
    </span>
  );

  if (!market.available) {
    return (
      <Card title={head("เงินเดือนและตลาดงาน")} actions={<FreshnessBadge market={market} />}>
        <p className="text-small text-text-muted">ยังไม่มีข้อมูลตลาดงานสำหรับสายงานนี้</p>
        {market.refreshing && <p className="mt-1 text-tiny text-text-muted">ระบบกำลังดึงข้อมูลตามรอบอัปเดต หน้านี้จะแสดงข้อมูลเองเมื่อพร้อม</p>}
      </Card>
    );
  }

  const layers = toLayers(market.salary);
  const ranges = [market.salary.advertised, market.salary.reference, market.salary.baseline].filter(Boolean);

  return (
    <>
      <Card title={head("เงินเดือน")} subtitle="แสดงแยกตามแหล่งที่มา ไม่มีตัวเลขใดเป็นเงินเดือนที่แท้จริง" actions={<FreshnessBadge market={market} />}>
        {layers.length > 0 && <SalaryRange layers={layers} roleTitle={roleTitle} />}
        <ul className="mt-2 divide-y divide-border">
          {ranges.map((r) => (
            <SalaryRow key={r.source_type} range={r} />
          ))}
        </ul>
        {!market.salary.reference && <p className="mt-2 text-tiny text-text-muted">ยังไม่มีตัวเลขอ้างอิงจากทีมสำหรับสายงานนี้</p>}
        <p className="mt-3 flex items-start gap-1.5 text-tiny text-info">
          <Info className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
          ตารางอ้างอิงจัดทำโดยทีมผู้พัฒนาจากแหล่งที่ระบุ · {market.disclaimer_th}
        </p>
      </Card>

      {market.demand && (
        <Card title={head("ความต้องการในตลาดงาน")} subtitle={`พบ ${num(market.demand.posting_count)} ประกาศในรอบล่าสุด`} actions={<FreshnessBadge market={market} />}>
          {market.demand.trending_skills.length > 0 && (
            <TrendingSkills
              roleTitle={roleTitle}
              owned={owned}
              data={{
                postings: market.demand.posting_count,
                skills: market.demand.trending_skills.map((s) => ({ skill_id: s.skill_id, name: s.name_th, count: s.count })),
              }}
            />
          )}
          {market.listings.length > 0 && (
            <section className="mt-6">
              <h3 className="mb-2 text-small font-semibold text-text">ตัวอย่างประกาศงาน</h3>
              <ul className="divide-y divide-border">
                {market.listings.map((l, i) => (
                  <li key={i} className="flex flex-wrap items-start justify-between gap-2 py-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-text">{l.title}</p>
                      <p className="text-small text-text-muted">
                        {l.company}
                        {l.location ? ` · ${l.location}` : ""}
                      </p>
                      <p className="text-tiny text-text-muted">
                        {l.salary_text ?? "ไม่ระบุเงินเดือน"}
                        {l.posted_at ? ` · ลงประกาศ ${dateTh(l.posted_at)}` : ""} · {l.source}
                      </p>
                    </div>
                    <a
                      href={l.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-3 text-small font-semibold text-accent hover:bg-bg"
                    >
                      ดูประกาศ
                      <ExternalLink className="size-3.5" strokeWidth={2} aria-hidden="true" />
                      <span className="sr-only">{`${l.title} (เปิดในแท็บใหม่)`}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <p className="mt-3 flex items-start gap-1.5 text-tiny text-info">
            <Info className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
            {market.disclaimer_th}
          </p>
        </Card>
      )}
    </>
  );
}
