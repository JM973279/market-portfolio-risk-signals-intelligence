"use client";
import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { DashboardData } from "@/lib/dashboard-types";
import { dashboardCopy, type CopyKey } from "@/lib/dashboard-copy";
import type { Language } from "@/lib/monitor-copy";
import { headerSnapshot, marketAsOf } from "@/lib/operational-status";
import { marketOrder } from "@/lib/market-order";

type Context = DashboardData & { language: Language; t: (key: CopyKey) => string };
const DashboardContext = createContext<Context | null>(null);
export function useDashboard() {
 const context = useContext(DashboardContext);
 if (!context) throw new Error("Dashboard provider is required");
 return context;
}
const navigation: { href: string; key: CopyKey; icon: string }[] = [
 { href:"/",key:"dashboard",icon:"M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9" },
 { href:"/us",key:"us",icon:"M4 4h16v16H4zM7 15l4-5 3 2 3-5" },
 { href:"/korea",key:"korea",icon:"M3 21h18M5 21V11h5v10M10 21V4h5v17M15 21v-8h4v8" },
 { href:"/portfolio",key:"portfolioAnalysis",icon:"M9 7V4h6v3M3 7h18v14H3zM3 12l9 3 9-3M12 12v5" },
 { href:"/breadth",key:"breadth",icon:"M4 20V10m5 10V4m6 16v-7m5 7V7M2 20h20" },
 { href:"/validation",key:"evidence",icon:"M4 5h16v15H4zM8 5V3m8 2V3M7 14l3 3 7-7" },
 { href:"/cases",key:"cases",icon:"M4 21V4h10l6 6v11zM14 4v6h6M8 14h8m-8 3h5" },
 { href:"/sources",key:"sources",icon:"M4 5c0-3 16-3 16 0v14c0 3-16 3-16 0zM4 5c0 3 16 3 16 0M4 12c0 3 16 3 16 0" },
 { href:"/methodology",key:"methodology",icon:"M3 4h7l2 2 2-2h7v16h-7l-2 2-2-2H3zM12 6v16M6 8h3m-3 4h3m6-4h3m-3 4h3" },
];
// 한국·미국 기준일을 따로 보여 준다. country가 있으면 그 시장만.
export function MarketDates({data, language, t, country}: {data: Pick<DashboardData, "operational">; language: Language; t: (key: CopyKey) => string; country?: "us" | "korea"}) {
 const markets = marketOrder(language).filter(c => !country || c === country);
 return <span className="market-dates">{markets.map(c => {
  const asOf = marketAsOf(data.operational?.markets[c]);
  return <span key={c}>{t(c === "korea" ? "marketKoreaShort" : "marketUsShort")} <b>{asOf.date ?? "N/A"}</b>{asOf.delayed && asOf.expected && asOf.expected !== asOf.date && <em title={`${t("dueDelayed")} ${asOf.expected}`}>{asOf.expected.slice(5)} {t("dueDelayed")}</em>}</span>;
 })}</span>;
}

export default function DashboardShell({ data, children }: { data: DashboardData; children: React.ReactNode }) {
 const [language, setLanguage] = useState<Language>("ko");
 const [open, setOpen] = useState(false);
 const pathname = usePathname();
 const t = (key: CopyKey) => dashboardCopy[key][language === "en" ? 0 : 1];
 const snapshot = headerSnapshot(data, pathname === "/us" ? "us" : pathname === "/korea" ? "korea" : undefined);
 // KR 화면은 한국 시장 → 미국 시장, EN 화면은 US → Korea 순서로 메뉴를 보여 준다.
 const order = marketOrder(language);
 const markets = navigation.filter(n => n.key === "us" || n.key === "korea")
  .sort((a, b) => order.indexOf(a.key as "us" | "korea") - order.indexOf(b.key as "us" | "korea"));
 const menu = navigation.flatMap(item => item.key === "us" ? markets : item.key === "korea" ? [] : [item]);
 useEffect(() => { document.documentElement.lang = language; }, [language, pathname]);
 useEffect(() => {
  const timer = setTimeout(() => {
   try { const saved = sessionStorage.getItem("mpri-language"); if (saved === "en" || saved === "ko") setLanguage(saved); } catch { /* Preference storage is optional. */ }
  }, 0);
  return () => clearTimeout(timer);
 }, []);
 const changeLanguage = (value: Language) => {
  setLanguage(value);
  try { sessionStorage.setItem("mpri-language", value); } catch { /* The toggle still works when storage is blocked. */ }
 };
 return <DashboardContext.Provider value={{...data,language,t}}><div className="app-shell">
  <aside className={`sidebar ${open ? "is-open" : ""}`}>
   <Link href="/" className="wordmark" aria-label="M/PRI home">M / PRI</Link>
   <p className="brand-description">Market &amp; Portfolio<br/>Risk Intelligence</p>
   <nav id="primary-navigation" aria-label={language === "ko" ? "주요 탐색" : "Main navigation"}>{menu.map(item => <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className={pathname === item.href ? "active" : ""} aria-current={pathname === item.href ? "page" : undefined}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={item.icon}/></svg>{t(item.key)}</Link>)}</nav>
   <div className="sidebar-bottom"><div className="sidebar-snapshot"><small>{t(snapshot.operational ? "operationalSnapshot" : "snapshot")}</small>{snapshot.operational ? <MarketDates data={data} language={language} t={t}/> : <b>{snapshot.date ?? "N/A"}</b>}<span className="live-label"><i/>{t("notLive")}</span></div><div className="language-toggle" role="group" aria-label={language === "ko" ? "언어 / Language" : "Language"}>{(["ko","en"] as const).map(lang => <button key={lang} lang={lang} aria-pressed={language===lang} onClick={() => changeLanguage(lang)}>{lang==="ko" ? "KR" : "EN"}</button>)}</div><small className="sidebar-research">{t("research")}</small></div>
  </aside>
  <div className="app-body"><div className="mobile-topbar"><Link href="/" className="wordmark">M / PRI</Link><button aria-label={t("menu")} aria-expanded={open} aria-controls="primary-navigation" onClick={() => setOpen(!open)}>☰</button></div>{open && <button className="nav-backdrop" aria-label={t("menu")} onClick={() => setOpen(false)}/>}{children}<footer><span>M / PRI <span className="footer-divider">/</span> {t("research")}</span><span>{t("footer")}</span></footer></div>
 </div></DashboardContext.Provider>;
}
