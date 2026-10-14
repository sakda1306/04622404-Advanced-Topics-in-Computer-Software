"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  CalendarDays,
  FileText,
  LogOut,
  MessageSquare,
  Plus,
  Shield,
  Trophy,
  Settings,
  Home,
  CircleCheck,
  ChartColumn,
} from "lucide-react";
import { useApp } from "./AppProvider";
import { PersonalSettings } from "./PersonalSettings";
import { MascotDock } from "./MascotDock";
import { ErrorBox, Loading } from "./Ui";
import { browseClubs } from "../lib/teams";
export function AppShell({ children }: { children: React.ReactNode }) {
  const app = useApp(),
    path = usePathname(),
    router = useRouter();
  const [historyOpen, setHistoryOpen] = useState(false);
  const browsing = app.browsingTeam ?? app.team;
  const authPage = path === "/login" || path === "/register",
    adminPage = path.startsWith("/admin");
  useEffect(() => {
    if (app.checked && !app.user && !authPage && !app.authError)
      router.replace("/login");
  }, [app.checked, app.user, app.authError, authPage, router]);
  const links = adminPage
    ? ([
        ["/admin", "ภาพรวม", BarChart3],
        ["/admin/pipeline", "Pipeline", CalendarDays],
        ["/admin/feedback", "Feedback", MessageSquare],
        ["/admin/logs", "Logs", FileText],
        ["/admin/reports", "ตรวจรายงาน", FileText],
        ["/admin/audit", "Audit", Shield],
        ["/admin/users", "ผู้ใช้", Shield],
        ["/admin/kb", "Knowledge Base", FileText],
        ["/", "กลับหน้าเว็บ", Trophy],
      ] as const)
    : ([
        ["/", "หน้าหลัก", Home],
        ["/football/fixtures", "ผลและโปรแกรมแข่ง", CalendarDays],
        ["/football/standings", "ตารางคะแนน", Trophy],
        ["/football/simulation", "ผลจำลองฤดูกาล", ChartColumn],
        ["/football/reports", "รายงานประจำสัปดาห์", FileText],
      ] as const);
  return (
    <div
      className={`site-shell ${authPage ? "" : "panball-shell"}`}
      style={
        {
          "--club": app.team.color,
          "--club-bright": app.team.colorBright,
          "--club-glow": app.team.glow,
          "--club-ink":
            app.team.key === "manchester-city" || app.team.key === "arsenal"
              ? "#080b11"
              : "#fff",
          "--club-stadium": "url(/backgrounds/" + app.team.key + ".png)",
        } as React.CSSProperties
      }
    >
      {process.env.NEXT_PUBLIC_DEMO_MODE === "true" && (
        <div className="demo-banner">
          โหมดสาธิต · ข้อมูลฟุตบอลและคำตอบ AI เป็นข้อมูลตัวอย่าง
        </div>
      )}
      <a className="skip-link" href="#content">
        ข้ามไปเนื้อหา
      </a>
      {authPage ? (
        children
      ) : !app.checked ? (
        <Loading />
      ) : app.authError ? (
        <div className="page-content">
          <ErrorBox error={app.authError} retry={() => void app.checkAuth()} />
        </div>
      ) : (
        app.user && (
          <>
            <aside className="site-sidebar">
              <Link href="/" className="wordmark">
                <img
                  className="panda-mark"
                  src="/panda-logo.svg"
                  alt=""
                  width={44}
                  height={44}
                />
                <span>
                  PANBALL
                  <small>
                    {adminPage ? "ADMIN CONSOLE" : "FOOTBALL INTELLIGENCE"}
                  </small>
                </span>
              </Link>
              <nav className="main-nav" aria-label="เมนูหลัก">
                {links.map(([href, label, Icon]) => (
                  <Link
                    key={href}
                    href={href}
                    className={path === href ? "active" : ""}
                    aria-current={path === href ? "page" : undefined}
                  >
                    <Icon size={19} />
                    {label}
                  </Link>
                ))}
                {!adminPage && app.user.role === "admin" && (
                  <Link href="/admin">
                    <Shield size={19} />
                    ผู้ดูแลระบบ
                  </Link>
                )}
              </nav>
              {!adminPage && (
                <section
                  className={`session-sidebar ${historyOpen ? "history-open" : ""}`}
                  aria-label="ประวัติการสนทนา"
                >
                  <div className="section-label">
                    <span className="desktop-history-label">บทสนทนาของคุณ</span>
                    <button
                      className="mobile-history-toggle"
                      aria-expanded={historyOpen}
                      onClick={() => setHistoryOpen((x) => !x)}
                    >
                      บทสนทนาของคุณ {historyOpen ? "−" : "+"}
                    </button>
                    <button
                      aria-label="เริ่มบทสนทนาใหม่"
                      onClick={() => {
                        app.newChat();
                        app.ask();
                      }}
                    >
                      <Plus size={18} />
                    </button>
                  </div>
                  <ErrorBox
                    error={app.historyError}
                    retry={() => void app.refreshSessions()}
                  />
                  {app.sessions.length === 0 && (
                    <p className="muted">ยังไม่มีบทสนทนา</p>
                  )}
                  {app.sessions.map((session) => (
                    <button
                      className={
                        app.sessionId === session.session_id ? "selected" : ""
                      }
                      key={session.session_id}
                      onClick={() => {
                        void app.selectSession(session.session_id);
                        app.ask();
                      }}
                    >
                      <MessageSquare size={14} />
                      <span>{session.title}</span>
                    </button>
                  ))}
                </section>
              )}
              <div className="sidebar-settings">
                <button onClick={() => app.setSettingsOpen(true)}>
                  <Settings size={19} />
                  ตั้งค่าส่วนตัว
                </button>
                <small className="favorite-club">
                  <img
                    src={`/crests/${app.team.teamId}.png`}
                    alt=""
                    width={28}
                    height={28}
                  />
                  ทีมโปรด · {app.team.shortName}
                </small>
              </div>
              <div className="sidebar-account">
                <span className="avatar">
                  {app.user.display_name.slice(0, 1)}
                </span>
                <div>
                  <strong>{app.user.display_name}</strong>
                  <small>
                    {app.user.role === "admin"
                      ? "ผู้ดูแลระบบ"
                      : "สมาชิก PANBALL"}
                  </small>
                </div>
                <button
                  aria-label="ออกจากระบบ"
                  onClick={() => void app.logout()}
                >
                  <LogOut size={18} />
                </button>
              </div>
            </aside>
            <div className="site-content">
              <header className="topbar">
                <span className="browse-label">
                  ดูข้อมูลทีม<small>กำลังดู · {browsing.shortName}</small>
                </span>
                <div
                  className="club-switcher"
                  role="group"
                  aria-label="เลือกดูข้อมูลทีม"
                >
                  {browseClubs.map((team) => (
                    <button
                      key={team.key}
                      aria-pressed={team.key === browsing.key}
                      onClick={() => app.browseTeam(team.key)}
                      title={team.name}
                    >
                      <img
                        className="club-crest"
                        src={"/crests/" + team.teamId + ".png"}
                        alt=""
                        width={28}
                        height={28}
                      />
                      <span>{team.shortName}</span>
                      {team.key === browsing.key && (
                        <CircleCheck
                          className="club-selected"
                          size={19}
                          aria-hidden="true"
                        />
                      )}
                    </button>
                  ))}
                </div>
              </header>
              {app.teamBusy && <p role="status">กำลังบันทึกทีมที่เชียร์…</p>}
              <ErrorBox error={app.teamError} />
              <main id="content" key={app.user.id}>
                {adminPage && app.user.role !== "admin" ? (
                  <div className="panel empty">
                    <h1>403 — ไม่มีสิทธิ์เข้าถึง</h1>
                    <p>หน้านี้สำหรับผู้ดูแลระบบ</p>
                    <Link href="/">กลับหน้าเว็บ</Link>
                  </div>
                ) : (
                  children
                )}
              </main>
              <footer>
                PANBALL · เวลาแสดงตามประเทศไทย ·
                ตรวจสอบแหล่งอ้างอิงและเวลาข้อมูล
              </footer>
            </div>
            <MascotDock />
            {app.settingsOpen && (
              <PersonalSettings
                key={app.user.id}
                close={() => app.setSettingsOpen(false)}
              />
            )}
          </>
        )
      )}
    </div>
  );
}
