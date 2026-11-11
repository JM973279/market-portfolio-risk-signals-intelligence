import localFont from "next/font/local";
import type { Metadata } from "next";
import DashboardShell from "@/components/dashboard-shell";
import { getDashboardData } from "@/lib/dashboard-data";
import "./globals.css";
const pretendard = localFont({src:"../../public/fonts/PretendardVariable.woff2",variable:"--font-pretendard",display:"swap",weight:"100 900"});
export const metadata: Metadata = {
 title: "M/PRI | Korea & US Market Stress Monitor",
 description: "한국·미국 시장의 과거 V1 위험, 관측 MSI 및 실험적 한국 신호 괴리 연구. Historical research, not live monitoring.",
};
export default async function RootLayout({children}: {children: React.ReactNode}) {
 const data = await getDashboardData();
 return <html lang="ko"><body className={pretendard.variable}><DashboardShell data={data}>{children}</DashboardShell></body></html>;
}
