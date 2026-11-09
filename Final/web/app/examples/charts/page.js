import { Info } from "lucide-react";
import { RequestsLine, ShareBars, StatTile, UsageMeters } from "@/components/charts/admin";
import { CompletenessSummary, MatchBreakdown, MatchSummary, TrendingSkills } from "@/components/charts/match";
import { SalaryRange } from "@/components/charts/salary-range";
import { SkillRadar } from "@/components/charts/skill-radar";
import { WorkStyleDumbbell } from "@/components/charts/work-style";
import {
  adminStats,
  breakdown,
  completeness,
  llmUsage,
  matchPct,
  requestsByDay,
  requiredSkills,
  role,
  routerShare,
  salary,
  trendingSkills,
  workStyle,
} from "@/lib/mock/charts";

export const metadata = {
  title: "ตัวอย่างกราฟ",
  robots: { index: false, follow: false },
};

// Chart examples with mock data, one of each chart in the DesignSystem charts plan.
export default function ChartExamples() {
  return (
    <div className="mx-auto w-full max-w-[1120px] px-4 py-10 md:px-6">
      <h1 className="text-h1 font-bold text-text">ตัวอย่างกราฟ</h1>
      <p className="mt-2 max-w-2xl text-body text-text-muted">
        กราฟทุกแบบที่จะใช้ในแอป ลองสลับธีมสว่าง/มืด ชี้ที่กราฟเพื่อดูรายละเอียด และกด “แสดงเป็นตาราง”
      </p>
      <p className="mt-4 inline-flex items-center gap-2 rounded-md border border-info px-3 py-2 text-small text-text">
        <Info className="size-4 text-info" strokeWidth={1.5} aria-hidden="true" />
        ข้อมูลทั้งหมดในหน้านี้เป็นข้อมูลสมมติ
      </p>

      <h2 className="mt-12 text-h2 font-semibold text-text">ฝั่งผู้ใช้</h2>
      <div className="mt-4 grid items-start gap-5 lg:grid-cols-2">
        <MatchSummary roleTitle={role.title_en} matchPct={matchPct} />
        <CompletenessSummary value={completeness} />
        <SkillRadar roleTitle={role.title_en} skills={requiredSkills} />
        <WorkStyleDumbbell traits={workStyle} roleTitle={role.title_en} />
        <MatchBreakdown parts={breakdown} matchPct={matchPct} />
        <TrendingSkills data={trendingSkills} roleTitle={role.title_en} />
        <div className="lg:col-span-2">
          <SalaryRange layers={salary} roleTitle={role.title_en} />
        </div>
      </div>

      <h2 className="mt-12 text-h2 font-semibold text-text">แดชบอร์ดผู้ดูแล</h2>
      <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {adminStats.map((s) => (
          <StatTile key={s.key} {...s} />
        ))}
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <UsageMeters items={llmUsage} />
        <ShareBars title="AI Router: สัดส่วนแต่ละ route" description="วันนี้ 812 ข้อความ" items={routerShare} labelKey="route" />
        <div className="lg:col-span-2">
          <RequestsLine byWindow={requestsByDay} />
        </div>
      </div>
    </div>
  );
}
