"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { MessageSquare, ThumbsUp, Clock, CircleAlert } from "lucide-react";
import { useApp } from "../../../components/AppProvider";
import { ErrorBox, Empty, Loading, PageTitle } from "../../../components/Ui";
import { Markdown, TraceView } from "../../../components/Answer";
import { api, body, isCancelled } from "../../../lib/api";
import { useRemote } from "../../../lib/use-remote";
import {
  dateTime,
  FootballStatus,
  Job,
  Page,
  Report,
  routeLabels,
  Source,
  Stats,
  Trace,
} from "../../../lib/types";
import { KnowledgeBase, Users } from "../../../components/AdminExtras";

export default function AdminPage({
  params,
}: {
  params: { section?: string[] };
}) {
  const app = useApp();
  if (app.user?.role !== "admin")
    return <Empty>403 — ไม่มีสิทธิ์เข้าถึง</Empty>;
  const section = params.section?.join("/") ?? "";
  if (!section) return <Dashboard />;
  if (section === "pipeline") return <Pipeline />;
  if (section === "feedback" || section === "logs" || section === "audit")
    return <Records key={section} kind={section} />;
  if (section === "reports") return <Reports />;
  if (section === "users") return <Users />;
  if (section === "kb") return <KnowledgeBase />;
  return <Empty>ไม่พบหน้า Admin นี้</Empty>;
}
function Dashboard() {
  const [days, setDays] = useState("7"),
    [revision, setRevision] = useState(0);
  const resource = useRemote<Stats>("/admin/stats?days=" + days, revision),
    stats = resource.data;
  return (
    <>
      <section className="hero admin-hero">
        <div className="hero-copy">
          <span className="eyebrow">YOUR CLUB. YOUR DATA.</span>
          <h1>CONTROL THE GAME</h1>
          <p>ติดตามการทำงานของผู้ช่วยฟุตบอล</p>
        </div>
      </section>
      <PageTitle eyebrow="ADMIN CONSOLE · สถิติทั้งระบบ" title="ภาพรวมระบบ">
        <label>
          ช่วงเวลา
          <select
            value={days}
            onChange={(event) => setDays(event.target.value)}
          >
            <option value="1">24 ชั่วโมงที่ผ่านมา</option>
            <option value="7">7 วันที่ผ่านมา</option>
            <option value="30">30 วันที่ผ่านมา</option>
          </select>
        </label>
        <button onClick={() => setRevision((value) => value + 1)}>
          รีเฟรช
        </button>
      </PageTitle>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorBox
          error={resource.error}
          retry={() => setRevision((value) => value + 1)}
        />
      ) : (
        stats && (
          <>
            <div className="metric-grid">
              {[
                ["ข้อความที่ตอบสำเร็จ", stats.total_messages.toLocaleString()],
                [
                  "Feedback เชิงบวก",
                  stats.feedback.up +
                    " / " +
                    (stats.feedback.up + stats.feedback.down),
                ],
                [
                  "Latency p50 / p95",
                  (stats.latency_ms.p50 / 1000).toFixed(1) +
                    "s / " +
                    (stats.latency_ms.p95 / 1000).toFixed(1) +
                    "s",
                ],
                ["ใช้คำตอบทางเลือก", stats.fallback_count.toLocaleString()],
              ].map(([label, value], index) => (
                <section className="panel metric" key={label}>
                  <span className="metric-icon" aria-hidden="true">
                    {
                      [
                        <MessageSquare key="m" />,
                        <ThumbsUp key="t" />,
                        <Clock key="c" />,
                        <CircleAlert key="a" />,
                      ][index]
                    }
                  </span>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </section>
              ))}
            </div>
            <div className="dashboard-grid">
              <Distribution title="เส้นทางการตอบ" data={stats.by_route} />
              <Distribution title="ชั้นที่ตัดสินใจ" data={stats.by_layer} />
            </div>
            <AdminSnapshot />
            <p className="muted">
              สถิติรวมในช่วงที่เลือก · Feedback นับเฉพาะคำตอบที่ผู้ใช้ให้คะแนน
            </p>
          </>
        )
      )}
    </>
  );
}
function AdminSnapshot() {
  const pipeline = useRemote<{ status: FootballStatus; jobs: Job[] }>(
    "/admin/pipeline",
  );
  const feedback = useRemote<Page<RecordItem>>("/admin/feedback?limit=3");
  return (
    <div className="dashboard-grid admin-snapshot">
      <section className="panel">
        <h2>Pipeline</h2>
        <p className="muted">การนำเข้าข้อมูลและงานประมวลผล</p>
        {pipeline.loading ? (
          <Loading />
        ) : pipeline.error ? (
          <ErrorBox error={pipeline.error} />
        ) : (
          <>
            <small>
              อัปเดตล่าสุด {dateTime(pipeline.data?.status.last_ingest_at)}
            </small>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>งาน</th>
                    <th>เริ่มต้น</th>
                    <th>สถานะ</th>
                  </tr>
                </thead>
                <tbody>
                  {pipeline.data?.jobs.slice(0, 3).map((job) => (
                    <tr key={job.job_id}>
                      <td>{job.scope ?? job.kind}</td>
                      <td>{dateTime(job.started_at)}</td>
                      <td>
                        <span className={"badge job-" + job.status}>
                          {jobLabels[job.status]}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!pipeline.data?.jobs.length && <p>ยังไม่มีงาน</p>}
          </>
        )}
        <Link className="button primary" href="/admin/pipeline">
          จัดการ Pipeline →
        </Link>
      </section>
      <section className="panel">
        <h2>Feedback ล่าสุด</h2>
        {feedback.loading ? (
          <Loading />
        ) : feedback.error ? (
          <ErrorBox error={feedback.error} />
        ) : feedback.data?.items.length ? (
          feedback.data.items.slice(0, 3).map((item, index) => (
            <div className="feedback-preview" key={item.message_id ?? index}>
              <MessageSquare size={20} aria-hidden="true" />
              <div>
                <p>
                  {item.comment ||
                    item.question ||
                    (item.rating === 1
                      ? "คำตอบนี้มีประโยชน์"
                      : "คำตอบนี้ควรปรับปรุง")}
                </p>
                <small>{dateTime(item.created_at)}</small>
              </div>
            </div>
          ))
        ) : (
          <p>ยังไม่มี Feedback</p>
        )}
        <Link className="text-link" href="/admin/feedback">
          ดู Feedback ทั้งหมด →
        </Link>
      </section>
    </div>
  );
}
function Distribution({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const max = Math.max(1, ...Object.values(data));
  return (
    <section className="panel">
      <h2>{title}</h2>
      {Object.keys(data).length ? (
        <ul className="distribution">
          {Object.entries(data).map(([key, value]) => (
            <li key={key}>
              <span>{routeLabels[key as keyof typeof routeLabels] ?? key}</span>
              <div className="bar-track" aria-hidden="true">
                <div style={{ width: (value / max) * 100 + "%" }} />
              </div>
              <strong>{value.toLocaleString()}</strong>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>ยังไม่มีข้อมูล</Empty>
      )}
    </section>
  );
}
const jobLabels: Record<string, string> = {
  queued: "รอดำเนินการ",
  running: "กำลังทำงาน",
  done: "สำเร็จ",
  failed: "ไม่สำเร็จ",
};
function Pipeline() {
  const [revision, setRevision] = useState(0),
    [scope, setScope] = useState("fixtures"),
    [season, setSeason] = useState(""),
    [week, setWeek] = useState(""),
    [jobId, setJobId] = useState<string>(),
    [job, setJob] = useState<Job>(),
    [error, setError] = useState<Error>(),
    [busy, setBusy] = useState(false);
  const resource = useRemote<{ status: FootballStatus; jobs: Job[] }>(
    "/admin/pipeline",
    revision,
  );
  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<Job>(
          "/admin/jobs/" + encodeURIComponent(jobId!),
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        setJob(next);
        setError(undefined);
        if (next.status === "done" || next.status === "failed") {
          setBusy(false);
          setRevision((value) => value + 1);
        } else timer = setTimeout(() => void poll(), 2000);
      } catch (error) {
        if (!controller.signal.aborted && !isCancelled(error)) {
          setError(error as Error);
          setBusy(false);
        }
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId]);
  async function run(path: string, payload: unknown) {
    setBusy(true);
    setError(undefined);
    setJob(undefined);
    try {
      const result = await api<{ job_id: string }>(path, body(payload));
      setJob({
        job_id: result.job_id,
        kind: path.includes("ingest") ? "ingest" : "weekly_report",
        status: "queued",
      });
      setJobId(result.job_id);
    } catch (error) {
      setError(error as Error);
      setBusy(false);
    }
  }
  const quota = resource.data?.status.quota;
  return (
    <>
      <PageTitle eyebrow="DATA OPERATIONS" title="Pipeline">
        <button onClick={() => setRevision((value) => value + 1)}>
          รีเฟรช
        </button>
      </PageTitle>
      <ErrorBox
        error={resource.error}
        retry={() => setRevision((value) => value + 1)}
      />
      <ErrorBox error={error} />
      {resource.loading && <Loading />}
      {resource.data && (
        <div className="status-strip">
          <span>
            ดึงข้อมูลล่าสุด {dateTime(resource.data.status.last_ingest_at)}
          </span>
          <span>
            โควตา API-Football {quota?.api_football_used_today ?? "—"} /{" "}
            {quota?.api_football_limit ?? "—"}
          </span>
        </div>
      )}
      <div className="dashboard-grid">
        <form
          className="panel stack"
          onSubmit={(event) => {
            event.preventDefault();
            void run("/admin/pipeline/ingest", { scope });
          }}
        >
          <h2>นำเข้าข้อมูล</h2>
          <label>
            ประเภท
            <select
              value={scope}
              onChange={(event) => setScope(event.target.value)}
            >
              <option value="fixtures">โปรแกรมและผลแข่งขัน</option>
              <option value="details">รายละเอียดการแข่งขัน</option>
              <option value="all">ทั้งหมด</option>
            </select>
          </label>
          <button className="primary" disabled={busy}>
            เริ่มดึงข้อมูล
          </button>
        </form>
        <form
          className="panel stack"
          onSubmit={(event) => {
            event.preventDefault();
            void run("/admin/reports/generate", {
              ...(season ? { season } : {}),
              ...(week ? { matchweek: Number(week) } : {}),
            });
          }}
        >
          <h2>สร้างรายงานประจำสัปดาห์</h2>
          <div className="form-row">
            <label>
              ฤดูกาล
              <input
                pattern="[0-9]{4}"
                maxLength={4}
                placeholder="ฤดูกาลปัจจุบัน"
                value={season}
                onChange={(event) => setSeason(event.target.value)}
              />
            </label>
            <label>
              แมตช์วีค
              <input
                type="number"
                min={1}
                max={38}
                placeholder="ล่าสุด"
                value={week}
                onChange={(event) => setWeek(event.target.value)}
              />
            </label>
          </div>
          <button className="primary" disabled={busy}>
            สร้างรายงาน
          </button>
        </form>
      </div>
      {job && (
        <section className="panel" role="status">
          <strong>{jobLabels[job.status]}</strong>
          <p>Job: {job.job_id}</p>
          {job.detail != null && (
            <p>
              {typeof job.detail === "string"
                ? job.detail
                : JSON.stringify(job.detail)}
            </p>
          )}
          {error && (
            <button
              onClick={() => {
                const id = jobId;
                setJobId(undefined);
                setTimeout(() => setJobId(id), 0);
              }}
            >
              ตรวจสถานะอีกครั้ง
            </button>
          )}
        </section>
      )}
      <section className="panel">
        <h2>งานล่าสุด</h2>
        {resource.data?.jobs.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>ประเภท</th>
                  <th>สถานะ</th>
                  <th>เริ่มเมื่อ</th>
                  <th>รายละเอียด</th>
                  <th>ตรวจสอบ</th>
                </tr>
              </thead>
              <tbody>
                {resource.data.jobs.map((item) => (
                  <tr key={item.job_id}>
                    <td>
                      {item.kind} {item.scope}
                    </td>
                    <td>
                      <span className={"badge " + item.status}>
                        {jobLabels[item.status] ?? item.status}
                      </span>
                    </td>
                    <td>{dateTime(item.started_at)}</td>
                    <td>
                      {typeof item.detail === "string"
                        ? item.detail
                        : item.detail
                          ? JSON.stringify(item.detail)
                          : "—"}
                    </td>
                    <td>
                      <button
                        onClick={() => {
                          setJob(item);
                          setJobId(item.job_id);
                          setBusy(
                            item.status === "queued" ||
                              item.status === "running",
                          );
                        }}
                      >
                        ดูสถานะ
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>ยังไม่มีงาน</Empty>
        )}
      </section>
    </>
  );
}
type RecordItem = {
  message_id?: string | null;
  request_id?: string;
  audit_id?: string;
  rating?: number;
  comment?: string | null;
  question?: string | null;
  answer_preview?: string;
  route?: string | null;
  fallback?: string | null;
  status?: number;
  error_code?: string | null;
  latency_ms?: number;
  created_at: string;
  user?: { username: string };
  actor?: { username: string };
  action?: string;
  target?: string | null;
  detail?: unknown;
};
type AdminMessage = {
  message_id: string;
  question?: string | null;
  answer: string;
  sources: Source[];
  trace?: Trace | null;
  created_at: string;
  request_id: string;
  route?: string;
  latency_ms?: number;
};
function Records({ kind }: { kind: "feedback" | "logs" | "audit" }) {
  const [days, setDays] = useState("7"),
    [rating, setRating] = useState(""),
    [route, setRoute] = useState(""),
    [fallback, setFallback] = useState(""),
    [requestId, setRequestId] = useState(""),
    [query, setQuery] = useState("days=7"),
    [cursor, setCursor] = useState(""),
    [selected, setSelected] = useState<string>(),
    [revision, setRevision] = useState(0);
  const resource = useRemote<Page<RecordItem>>(
      "/admin/" +
        kind +
        "?" +
        query +
        (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
      revision,
    ),
    message = useRemote<AdminMessage>(
      selected ? "/admin/messages/" + selected : null,
    );
  return (
    <>
      <PageTitle
        eyebrow="OBSERVABILITY"
        title={
          {
            feedback: "Feedback ของผู้ใช้",
            logs: "บันทึกการตอบคำถาม",
            audit: "ประวัติการจัดการระบบ",
          }[kind]
        }
      />
      <form
        className="panel filter-bar"
        onSubmit={(event) => {
          event.preventDefault();
          const search = new URLSearchParams({ days, limit: "25" });
          if (rating) search.set("rating", rating);
          if (route) search.set("route", route);
          if (fallback) search.set("fallback", fallback);
          if (requestId)
            search.set(kind === "audit" ? "action" : "request_id", requestId);
          setQuery(search.toString());
          setCursor("");
          setSelected(undefined);
          setRevision((value) => value + 1);
        }}
      >
        <label>
          ย้อนหลัง (วัน)
          <input
            required
            type="number"
            min={1}
            max={90}
            value={days}
            onChange={(event) => setDays(event.target.value)}
          />
        </label>
        {kind === "feedback" && (
          <label>
            คะแนน
            <select
              value={rating}
              onChange={(event) => setRating(event.target.value)}
            >
              <option value="">ทั้งหมด</option>
              <option value="1">ถูกใจ</option>
              <option value="-1">ไม่ถูกใจ</option>
            </select>
          </label>
        )}
        {kind !== "audit" && (
          <label>
            เส้นทาง
            <select
              value={route}
              onChange={(event) => setRoute(event.target.value)}
            >
              <option value="">ทั้งหมด</option>
              {Object.entries(routeLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}
        {kind === "logs" && (
          <label>
            ทางเลือก
            <select
              value={fallback}
              onChange={(event) => setFallback(event.target.value)}
            >
              <option value="">ทั้งหมด</option>
              <option value="any">มี fallback</option>
              <option value="retrieval_empty">ไม่พบข้อมูล</option>
              <option value="retrieval_down">คลังไม่พร้อม</option>
              <option value="llm_fallback_provider">เปลี่ยนผู้ให้บริการ</option>
            </select>
          </label>
        )}
        {kind !== "feedback" && (
          <label>
            {kind === "audit" ? "Action" : "Request ID"}
            <input
              maxLength={64}
              value={requestId}
              onChange={(event) => setRequestId(event.target.value)}
            />
          </label>
        )}
        <button className="primary">ค้นหา</button>
      </form>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorBox
          error={resource.error}
          retry={() => setRevision((value) => value + 1)}
        />
      ) : (
        <section className="panel">
          {resource.data?.items.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>เวลา</th>
                    <th>ผู้ใช้ / รหัสคำขอ</th>
                    <th>รายละเอียด</th>
                    <th>สถานะ</th>
                    <th>ดูคำตอบ</th>
                  </tr>
                </thead>
                <tbody>
                  {resource.data.items.map((item, index) => (
                    <tr
                      key={
                        item.audit_id ??
                        item.message_id ??
                        item.request_id ??
                        index
                      }
                    >
                      <td>{dateTime(item.created_at)}</td>
                      <td>
                        {item.user?.username ??
                          item.actor?.username ??
                          item.request_id ??
                          "—"}
                      </td>
                      <td>
                        {kind === "audit" ? (
                          <>
                            <strong>{item.action}</strong>
                            <p>{item.target}</p>
                            <details>
                              <summary>รายละเอียด</summary>
                              <pre>{JSON.stringify(item.detail, null, 2)}</pre>
                              <small>{item.request_id}</small>
                            </details>
                          </>
                        ) : (
                          <>
                            <p>
                              {item.question ??
                                item.answer_preview ??
                                item.error_code ??
                                "—"}
                            </p>
                            {item.comment && <p>{item.comment}</p>}
                            <small>
                              {routeLabels[
                                item.route as keyof typeof routeLabels
                              ] ?? item.route}{" "}
                              {item.fallback}
                            </small>
                          </>
                        )}
                      </td>
                      <td>
                        {item.rating === 1
                          ? "ถูกใจ"
                          : item.rating === -1
                            ? "ไม่ถูกใจ"
                            : (item.status ?? "บันทึกแล้ว")}
                      </td>
                      <td>
                        {item.message_id && (
                          <button onClick={() => setSelected(item.message_id!)}>
                            เปิดคำตอบ
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>ไม่มีรายการตรงกับตัวกรอง</Empty>
          )}
          <div className="pagination">
            <button disabled={!cursor} onClick={() => setCursor("")}>
              กลับหน้าแรก
            </button>
            <button
              disabled={!resource.data?.next_cursor}
              onClick={() => setCursor(resource.data!.next_cursor!)}
            >
              หน้าถัดไป
            </button>
          </div>
        </section>
      )}
      {selected && (
        <section className="panel">
          <header className="panel-heading">
            <h2>รายละเอียดคำตอบ</h2>
            <button onClick={() => setSelected(undefined)}>
              ปิดรายละเอียด
            </button>
          </header>
          {message.loading ? (
            <Loading />
          ) : message.error ? (
            <ErrorBox error={message.error} />
          ) : (
            message.data && (
              <>
                <p className="muted">Request ID: {message.data.request_id}</p>
                <blockquote>{message.data.question}</blockquote>
                <Markdown
                  text={message.data.answer}
                  sources={message.data.sources}
                  prefix={"admin-" + selected}
                />
                <ol className="sources">
                  {message.data.sources.map((source) => (
                    <li
                      tabIndex={-1}
                      id={"admin-" + selected + "-source-" + source.ref}
                      key={source.ref}
                    >
                      [{source.ref}] {source.title}
                      <small>{source.origin}</small>
                    </li>
                  ))}
                </ol>
                <TraceView trace={message.data.trace} />
              </>
            )
          )}
        </section>
      )}
    </>
  );
}
function Reports() {
  const [status, setStatus] = useState("draft"),
    [season, setSeason] = useState(""),
    [query, setQuery] = useState("status=draft"),
    [revision, setRevision] = useState(0),
    [selected, setSelected] = useState<Report>();
  const resource = useRemote<{ items: Report[] }>(
    "/admin/reports?" + query,
    revision,
  );
  return (
    <>
      <PageTitle eyebrow="EDITORIAL DESK" title="ตรวจรายงานประจำสัปดาห์" />
      <form
        className="panel filter-bar"
        onSubmit={(event) => {
          event.preventDefault();
          const search = new URLSearchParams({ status });
          if (season) search.set("season", season);
          setQuery(search.toString());
          setSelected(undefined);
          setRevision((value) => value + 1);
        }}
      >
        <label>
          สถานะ
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="draft">ร่าง</option>
            <option value="published">เผยแพร่แล้ว</option>
            <option value="unpublished">ถอนการเผยแพร่</option>
          </select>
        </label>
        <label>
          ฤดูกาล
          <input
            pattern="[0-9]{4}"
            value={season}
            onChange={(event) => setSeason(event.target.value)}
          />
        </label>
        <button className="primary">แสดงรายงาน</button>
      </form>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorBox
          error={resource.error}
          retry={() => setRevision((value) => value + 1)}
        />
      ) : (
        <section className="panel">
          {resource.data?.items.length ? (
            resource.data.items.map((report) => (
              <button
                className="report-row"
                key={report.season + report.matchweek}
                onClick={() => setSelected(report)}
              >
                <span>{report.title}</span>
                <span>
                  นัดที่ {report.matchweek} · {report.status}
                </span>
              </button>
            ))
          ) : (
            <Empty>ไม่มีรายงานในสถานะนี้</Empty>
          )}
        </section>
      )}
      {selected && (
        <ReportEditor
          key={selected.season + "-" + selected.matchweek}
          initial={selected}
          onUpdate={() => setRevision((value) => value + 1)}
        />
      )}
    </>
  );
}
function ReportEditor({
  initial,
  onUpdate,
}: {
  initial: Report;
  onUpdate: () => void;
}) {
  const [report, setReport] = useState(initial),
    [title, setTitle] = useState(initial.title),
    [markdown, setMarkdown] = useState(initial.markdown),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>(),
    [notice, setNotice] = useState("");
  async function action(kind: "save" | "publish" | "unpublish") {
    if (
      kind === "unpublish" &&
      !window.confirm("ถอนการเผยแพร่รายงานนี้? ผู้ใช้ทั่วไปจะไม่เห็นรายงานนี้")
    )
      return;
    setBusy(true);
    setError(undefined);
    setNotice("");
    try {
      const path = "/admin/reports/" + report.season + "/" + report.matchweek;
      const next = await api<Report>(
        path + (kind === "save" ? "" : "/" + kind),
        kind === "save"
          ? { method: "PATCH", body: JSON.stringify({ title, markdown }) }
          : { method: "POST" },
      );
      setReport(next);
      setTitle(next.title);
      setMarkdown(next.markdown);
      setNotice("บันทึกเรียบร้อย");
      onUpdate();
    } catch (error) {
      setError(error as Error);
    } finally {
      setBusy(false);
    }
  }
  const dirty = title !== report.title || markdown !== report.markdown;
  return (
    <section className="panel stack">
      <h2>แก้ไขและตรวจรายงาน</h2>
      <span className="badge">{report.status}</span>
      <label>
        หัวข้อ
        <input
          maxLength={200}
          value={title}
          disabled={report.status === "published" || busy}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label>
        เนื้อหา Markdown
        <textarea
          rows={12}
          maxLength={50000}
          value={markdown}
          disabled={report.status === "published" || busy}
          onChange={(event) => setMarkdown(event.target.value)}
        />
      </label>
      <div className="button-row">
        <button
          disabled={
            busy ||
            report.status === "published" ||
            !title.trim() ||
            !markdown.trim()
          }
          onClick={() => void action("save")}
        >
          บันทึกการแก้ไข
        </button>
        {report.status === "published" ? (
          <button disabled={busy} onClick={() => void action("unpublish")}>
            ถอนการเผยแพร่
          </button>
        ) : (
          <button
            className="primary"
            disabled={busy || dirty}
            onClick={() => void action("publish")}
          >
            เผยแพร่
          </button>
        )}
      </div>
      {dirty && <small>บันทึกการแก้ไขก่อนเผยแพร่</small>}
      <ErrorBox error={error} />
      {notice && <p role="status">{notice}</p>}
      <details>
        <summary>ดูตัวอย่าง</summary>
        <h2>{title}</h2>
        <Markdown text={markdown} />
      </details>
    </section>
  );
}
