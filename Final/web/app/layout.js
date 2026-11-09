import { Anuphan, Urbanist } from "next/font/google";
import { ThemeProvider } from "@/components/theme-provider";
import { TopBar } from "@/components/top-bar";
import { MockToolbar } from "@/components/app/mock-toolbar";
import { PageTransitionProvider } from "@/components/motion/page-transition";
import { AppBackground } from "@/components/app/app-background";
import { Suspense } from "react";
import { APP_NAME } from "@/lib/config";
import "./globals.css";

// Brand fonts (CIBrand.md section 4): Anuphan for Thai, Urbanist for Latin.
const thai = Anuphan({
  subsets: ["thai", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-thai",
  display: "swap",
});

const latin = Urbanist({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-latin",
  display: "swap",
});

export const metadata = {
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: "เข้าใจตัวเองก่อน แล้วงานที่ใช่จะชัดขึ้น",
};

export const viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0c1922" },
  ],
};

export default function RootLayout({ children }) {
  return (
    // suppressHydrationWarning: next-themes sets the theme class before React hydrates
    <html lang="th" className={`${thai.variable} ${latin.variable}`} suppressHydrationWarning>
      <body className="flex min-h-dvh flex-col">
        <ThemeProvider>
          {/* AppBackground reads the path (usePathname), which needs a Suspense boundary on dynamic routes */}
          <Suspense fallback={null}>
            <AppBackground />
          </Suspense>
          <PageTransitionProvider>
            <TopBar appName={APP_NAME} />
            <main className="flex flex-1 flex-col">{children}</main>
            <MockToolbar />
          </PageTransitionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
