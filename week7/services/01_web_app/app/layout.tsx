import type { Metadata } from "next";
import "./globals.css";
import "./panball.css";
import "./prediction.css";
import { AppProvider } from "../components/AppProvider";
import { AppShell } from "../components/AppShell";

export const metadata: Metadata = {
  title: "PANBALL | Football Assistant",
  icons: { icon: "/panda-logo.svg" },
  description: "ผู้ช่วยฟุตบอลพรีเมียร์ลีก พร้อมคำตอบและแหล่งอ้างอิง",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="th">
      <body>
        <AppProvider>
          <AppShell>{children}</AppShell>
        </AppProvider>
      </body>
    </html>
  );
}
