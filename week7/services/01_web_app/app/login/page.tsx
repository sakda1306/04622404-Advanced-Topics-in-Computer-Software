"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { AuthStory } from "../../components/AuthStory";
import { useApp } from "../../components/AppProvider";
import { ErrorBox } from "../../components/Ui";
export default function Login() {
  const app = useApp();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error>();
  return (
    <main className="login-page" id="content">
      <AuthStory />
      <section className="login-form-area">
        <div className="login-form">
          {app.loggingOut && (
            <p role="status">กำลังออกจากระบบ กรุณารอสักครู่</p>
          )}
          <span className="eyebrow">WELCOME TO PANBALL</span>
          <h2>ยินดีต้อนรับกลับ</h2>
          <p className="muted">เข้าสู่ระบบ PANBALL</p>
          {app.user ? (
            <>
              <p>เข้าสู่ระบบแล้ว: {app.user.display_name}</p>
              <Link href="/" className="button primary">
                กลับหน้าเว็บ <ArrowRight size={18} />
              </Link>
            </>
          ) : (
            <form
              onSubmit={async (event) => {
                event.preventDefault();
                setError(undefined);
                setPending(true);
                try {
                  await app.login(username, password);
                  setPassword("");
                } catch (error) {
                  setError(error as Error);
                } finally {
                  setPending(false);
                }
              }}
            >
              <label>
                ชื่อผู้ใช้
                <input
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              </label>
              <label>
                รหัสผ่าน
                <div className="password-field">
                  <input
                    autoComplete="current-password"
                    required
                    type={visible ? "text" : "password"}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                  <button
                    type="button"
                    aria-label={visible ? "ซ่อนรหัสผ่าน" : "แสดงรหัสผ่าน"}
                    onClick={() => setVisible(!visible)}
                  >
                    {visible ? <EyeOff size={20} /> : <Eye size={20} />}
                  </button>
                </div>
              </label>
              <ErrorBox error={error ?? app.authError} />
              <button
                className="primary login-submit"
                disabled={pending || app.loggingOut || !app.checked}
              >
                {app.loggingOut
                  ? "กำลังออกจากระบบ…"
                  : pending
                    ? "กำลังเข้าสู่ระบบ…"
                    : "เข้าสู่ระบบ"}
                <ArrowRight size={20} />
              </button>
            </form>
          )}
          <p className="auth-switch">
            ยังไม่มีบัญชี? <Link href="/register">สมัครสมาชิก</Link>
          </p>
          <div
            className="login-pet"
            role="img"
            aria-label={"มาสคอส " + app.team.name}
            style={{ backgroundImage: "url(" + app.team.mascot + ")" }}
          />
        </div>
      </section>
    </main>
  );
}
