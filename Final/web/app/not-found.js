import Link from "next/link";

export const metadata = { title: "ไม่พบหน้านี้" };

// Shown for any address the site does not have (DesignSystem.md section 5: Thai copy).
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="text-h2 font-semibold text-text">ไม่พบหน้านี้</h1>
      <p className="text-small text-text-muted">ลิงก์อาจไม่ถูกต้อง หรือหน้านี้ถูกย้ายไปแล้ว</p>
      <Link href="/" className="text-small font-semibold text-accent hover:underline">
        กลับหน้าแรก
      </Link>
    </main>
  );
}
