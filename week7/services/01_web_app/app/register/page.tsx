"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { AuthStory } from "../../components/AuthStory";
import { useApp } from "../../components/AppProvider";
import { ErrorBox } from "../../components/Ui";

export default function Register() {
  const app = useApp();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error>();
  const [passwordError, setPasswordError] = useState("");

  return (
    <main className="login-page" id="content">
      <AuthStory />
      <section className="login-form-area">
        <div className="login-form">
          <span className="eyebrow">JOIN PANBALL</span>
          <h2>สมัครสมาชิก</h2>
          <p className="muted">สร้างบัญชีเพื่อติดตามทีมที่คุณรัก</p>
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
                if (password !== confirmation) {
                  setPasswordError("รหัสผ่านทั้งสองช่องไม่ตรงกัน");
                  return;
                }
                setPasswordError("");
                setPending(true);
                try {
                  await app.register(username, displayName, password);
                  setPassword("");
                  setConfirmation("");
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
                  minLength={3}
                  maxLength={32}
                  pattern="[A-Za-z0-9_]+"
                  title="ใช้อักษรอังกฤษ ตัวเลข หรือ _ จำนวน 3–32 ตัว"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
                <span className="auth-hint">
                  อักษรอังกฤษ ตัวเลข หรือ _ จำนวน 3–32 ตัว
                </span>
              </label>
              <label>
                ชื่อที่แสดง
                <input
                  autoComplete="nickname"
                  required
                  maxLength={120}
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                />
              </label>
              <label>
                รหัสผ่าน
                <div className="password-field">
                  <input
                    autoComplete="new-password"
                    required
                    minLength={8}
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
                <span className="auth-hint">
                  อย่างน้อย 8 ตัวอักษร ไม่เกิน 72 ไบต์
                </span>
              </label>
              <label>
                ยืนยันรหัสผ่าน
                <input
                  autoComplete="new-password"
                  required
                  type={visible ? "text" : "password"}
                  aria-invalid={Boolean(passwordError)}
                  aria-describedby={
                    passwordError ? "password-error" : undefined
                  }
                  value={confirmation}
                  onChange={(event) => {
                    setConfirmation(event.target.value);
                    setPasswordError("");
                  }}
                />
                {passwordError && (
                  <span
                    id="password-error"
                    className="auth-field-error"
                    role="alert"
                  >
                    {passwordError}
                  </span>
                )}
              </label>
              <ErrorBox error={error} />
              <button
                className="primary login-submit"
                disabled={pending || !app.checked}
              >
                {pending ? "กำลังสมัครสมาชิก…" : "สมัครสมาชิก"}
                <ArrowRight size={20} />
              </button>
            </form>
          )}
          <p className="auth-switch">
            มีบัญชีแล้ว? <Link href="/login">เข้าสู่ระบบ</Link>
          </p>
        </div>
      </section>
    </main>
  );
}
