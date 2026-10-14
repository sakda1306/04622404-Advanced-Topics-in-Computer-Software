"use client";
import { ApiError } from "../lib/api";
export function ErrorBox({
  error,
  retry,
}: {
  error?: Error;
  retry?: () => void;
}) {
  if (!error) return null;
  const message =
    error instanceof ApiError && error.code === "INDEX_NOT_READY"
      ? "คลังข้อมูลกำลังเตรียมพร้อม กรุณารอสักครู่แล้วลองใหม่"
      : error instanceof ApiError && error.code === "RETRIEVAL_UNAVAILABLE"
        ? "เชื่อมต่อคลังข้อมูลไม่ได้ชั่วคราว กรุณาลองใหม่ภายหลัง"
        : error.message || "เชื่อมต่อไม่สำเร็จ";
  return (
    <div className="error-box" role="alert">
      <strong>{message}</strong>
      {error instanceof ApiError && (
        <>
          <small>
            {error.retryAfter
              ? "กรุณารอ " + error.retryAfter + " วินาที"
              : error.code}
          </small>
          {error.requestId && <small>Request ID: {error.requestId}</small>}
        </>
      )}
      {retry && <button onClick={retry}>ลองใหม่</button>}
    </div>
  );
}
export function Loading() {
  return (
    <p role="status" className="empty">
      กำลังโหลดข้อมูล…
    </p>
  );
}
export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}
export function PageTitle({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
      </div>
      {children}
    </header>
  );
}
