"use client";
import { useState } from "react";
import { api, body } from "../lib/api";
import { Page, dateTime } from "../lib/types";
import { useRemote } from "../lib/use-remote";
import { useApp } from "./AppProvider";
import { Empty, ErrorBox, Loading, PageTitle } from "./Ui";
type AdminUser = {
  id: string;
  username: string;
  display_name: string;
  role: "user" | "admin";
  disabled: boolean;
  message_count: number;
  last_login_at?: string | null;
};
export function Users() {
  const app = useApp();
  const [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [cursor, setCursor] = useState(""),
    [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>();
  const resource = useRemote<Page<AdminUser>>(
    "/admin/users?q=" +
      encodeURIComponent(query) +
      "&limit=25" +
      (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
    revision,
  );
  async function update(
    user: AdminUser,
    patch: { role?: string; disabled?: boolean },
  ) {
    if (user.id === app.user?.id) return;
    if (
      patch.disabled &&
      !window.confirm(
        "ระงับบัญชี " + user.username + "? ผู้ใช้นี้จะเข้าสู่ระบบไม่ได้",
      )
    )
      return;
    setBusy(true);
    setError(undefined);
    try {
      await api("/admin/users/" + user.id, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setRevision((value) => value + 1);
    } catch (error) {
      setError(error as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageTitle eyebrow="ACCOUNT MANAGEMENT" title="จัดการผู้ใช้" />
      <form
        className="panel filter-bar"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(search);
          setCursor("");
          setRevision((value) => value + 1);
        }}
      >
        <label>
          ค้นหาชื่อผู้ใช้
          <input
            value={search}
            maxLength={64}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <button className="primary">ค้นหา</button>
      </form>
      <ErrorBox error={error} />
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorBox
          error={resource.error}
          retry={() => setRevision((value) => value + 1)}
        />
      ) : (
        <section className="panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>ผู้ใช้</th>
                  <th>บทบาท</th>
                  <th>จำนวนข้อความ</th>
                  <th>เข้าระบบล่าสุด</th>
                  <th>สถานะ</th>
                </tr>
              </thead>
              <tbody>
                {resource.data?.items.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <strong>{user.display_name}</strong>
                      <small className="block">{user.username}</small>
                    </td>
                    <td>
                      <select
                        aria-label={"บทบาท " + user.username}
                        value={user.role}
                        disabled={busy || user.id === app.user?.id}
                        onChange={(event) =>
                          void update(user, { role: event.target.value })
                        }
                      >
                        <option value="user">ผู้ใช้</option>
                        <option value="admin">ผู้ดูแลระบบ</option>
                      </select>
                    </td>
                    <td>{user.message_count}</td>
                    <td>{dateTime(user.last_login_at)}</td>
                    <td>
                      <button
                        disabled={busy || user.id === app.user?.id}
                        onClick={() =>
                          void update(user, { disabled: !user.disabled })
                        }
                      >
                        {user.disabled ? "ปลดระงับ" : "ระงับบัญชี"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!resource.data?.items.length && <Empty>ไม่พบผู้ใช้</Empty>}
          <p className="muted">ไม่สามารถเปลี่ยนสิทธิ์หรือระงับบัญชีตนเองได้</p>
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
    </>
  );
}
export function KnowledgeBase() {
  const [revision, setRevision] = useState(0),
    [category, setCategory] = useState(""),
    [docId, setDocId] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error>(),
    [notice, setNotice] = useState("");
  const resource = useRemote<{
    documents: number;
    chunks: number;
    by_category: Record<string, number>;
    index_version: string;
  }>("/admin/kb/stats", revision);
  async function rebuild() {
    setBusy(true);
    setError(undefined);
    setNotice("");
    try {
      const result = await api<{ job_id: string }>(
        "/admin/kb/reindex",
        body(category ? { category } : {}),
      );
      setNotice(
        "รับคำขอสร้างดัชนีแล้ว · Job: " +
          result.job_id +
          " · ยังไม่ใช่การยืนยันว่าเสร็จสิ้น",
      );
    } catch (error) {
      setError(error as Error);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (
      !docId.trim() ||
      !window.confirm("ลบเอกสาร " + docId + " ออกจากคลังข้อมูล?")
    )
      return;
    setBusy(true);
    setError(undefined);
    setNotice("");
    try {
      const result = await api<{ deleted: boolean }>(
        "/admin/kb/documents/" + encodeURIComponent(docId.trim()),
        { method: "DELETE" },
      );
      setNotice(result.deleted ? "ลบเอกสารแล้ว" : "ไม่พบเอกสารนี้ในคลัง");
      setDocId("");
      setRevision((value) => value + 1);
    } catch (error) {
      setError(error as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageTitle eyebrow="KNOWLEDGE OPERATIONS" title="Knowledge Base">
        <button onClick={() => setRevision((value) => value + 1)}>
          รีเฟรช
        </button>
      </PageTitle>
      <ErrorBox
        error={resource.error}
        retry={() => setRevision((value) => value + 1)}
      />
      <ErrorBox error={error} />
      {notice && (
        <p className="panel" role="status">
          {notice}
        </p>
      )}
      {resource.loading ? (
        <Loading />
      ) : (
        resource.data && (
          <section className="panel">
            <div className="metric-grid">
              <div className="metric">
                <span>เอกสาร</span>
                <strong>{resource.data.documents}</strong>
              </div>
              <div className="metric">
                <span>Chunks</span>
                <strong>{resource.data.chunks}</strong>
              </div>
            </div>
            <p className="muted">
              Index version: {resource.data.index_version}
            </p>
            <dl className="data-list">
              {Object.entries(resource.data.by_category).map(([key, count]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{count}</dd>
                </div>
              ))}
            </dl>
          </section>
        )
      )}
      <div className="dashboard-grid">
        <form
          className="panel stack"
          onSubmit={(event) => {
            event.preventDefault();
            void rebuild();
          }}
        >
          <h2>สร้างดัชนีใหม่</h2>
          <label>
            ประเภท
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">ทั้งหมด</option>
              {[
                "trivia",
                "match_report",
                "standings",
                "fixtures",
                "weekly_report",
                "player",
                "historical",
              ].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={busy}>
            เริ่มสร้างดัชนี
          </button>
        </form>
        <form
          className="panel stack"
          onSubmit={(event) => {
            event.preventDefault();
            void remove();
          }}
        >
          <h2>ลบเอกสารทีละรายการ</h2>
          <label>
            Document ID
            <input
              required
              maxLength={120}
              pattern="[A-Za-z0-9._-]+"
              value={docId}
              onChange={(event) => setDocId(event.target.value)}
            />
          </label>
          <button disabled={busy || !docId.trim()}>ลบเอกสาร</button>
        </form>
      </div>
    </>
  );
}
