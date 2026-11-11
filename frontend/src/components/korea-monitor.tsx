"use client";

import { useEffect, useState } from "react";
import { copy, reasonCopy, stateCopy, signalCopy, stateRules, type Language } from "@/lib/monitor-copy";

type Row = {
  Date: string; Prob_XGBoost: number | null; Korea_MSI: number | null; Stress_Threshold: number | null;
  extreme_count: number | null; persistent: number | null; window_hits: number | null;
  breadth_mean: number | null; correlation_count: number | null;
  state: string; reason: string; mode: string;
  reported_v1_percent?: number; reported_return_percent?: number;
  [key: string]: string | number | null | undefined;
};
export type MonitorData = {
  dataset: string; history: Row[]; holdout: Row[]; latest: Row | null; last_complete: Row | null;
  issues: string[]; sources: Record<string, { path: string; latest: string | null; rows: number; sha256?: string }>;
  evidence: { eligible: number; detected: number; coverage: number; median_lead: number; false_warnings_year: number; status: string; source: string };
};
function tone(state: string) { return state === "NORMAL" ? "normal" : state.includes("UNKNOWN") ? "unknown" : "warning"; }

export default function KoreaMonitor({ data }: { data: MonitorData | null }) {
  const [language, setLanguage] = useState<Language>("en");
  const index = language === "en" ? 0 : 1;
  const t = (key: keyof typeof copy) => copy[key][index];
  const number = (n: unknown, digits = 3) => typeof n === "number" ? n.toFixed(digits) : t("unavailable");
  const percent = (n: unknown) => typeof n === "number" ? `${(n * 100).toFixed(1)}%` : t("unavailable");
  const state = (s: string) => stateCopy[s]?.[index] ?? s;
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  const languageToggle = <div className="language-toggle" role="group" aria-label="Language / 언어">{(["ko", "en"] as const).map(lang => <button key={lang} aria-pressed={language === lang} onClick={() => setLanguage(lang)}>{lang === "ko" ? "KR" : "EN"}</button>)}</div>;
  const [selected, setSelected] = useState(data?.latest?.Date ?? "");
  const [window, setWindow] = useState(120);
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const first = setTimeout(() => setNow(Date.now()), 0);
    const tick = setInterval(() => setNow(Date.now()), 60000);
    return () => { clearTimeout(first); clearInterval(tick); };
  }, []);
  if (!data) return <main className="shell"><header><b>{t("product")}</b>{languageToggle}</header><section><span className="badge">{t("research")}</span><h1>{t("unavailable")}</h1><p>{t("missingExport")}</p></section></main>;
  const row = data.history.find(r => r.Date === selected) ?? null;
  const end = data.history.findIndex(r => r.Date === selected);
  const chart = data.history.slice(Math.max(0, end - window + 1), end + 1);
  const corr = row?.correlation_count;
  const latestDate = data.latest?.Date;
  const elapsed = latestDate && now !== null ? Math.floor((now - new Date(`${latestDate}T00:00:00+09:00`).getTime()) / 86400000) : null;
  return <div className="shell">
    <header><a className="brand" href="#">M<span> / </span>PRI</a><span className="product-name">{t("product")}<small>Market &amp; Portfolio Risk Intelligence</small></span><span className="badge">{t("research")}</span>{languageToggle}</header>
    <nav aria-label={language === "en" ? "Page sections" : "페이지 섹션"}><a href="#status">{t("nav")}</a><a href="#breadth">{t("breadth")}</a><a href="#evidence">{t("evidence")}</a><a href="#holdout">{t("holdout")}</a></nav>
    <main>
      <div className="heading"><div><p className="eyebrow">{t("eyebrow")}</p><h1>{t("title")}</h1><p>{t("subtitle")}</p></div><div className="reference">{t("reference")} <b>{t("frozen")}</b><small>{t("champion")}</small></div></div>
      <aside className="data-strip"><b>{t("historical")}</b><p>{t("latest")}: {latestDate ?? t("unavailable")}. {elapsed !== null && <>{t("freshness")}: {elapsed}. </>}{t("calendar")} V1: {data.sources.v1?.latest ?? t("unavailable")}; MSI: {data.sources.msi?.latest ?? t("unavailable")}. {t("complete")}: {data.last_complete?.Date ?? t("unavailable")}.</p></aside>
      {data.issues.length > 0 && <aside className="notice warning"><b>{t("missing")}</b>{data.issues.map(i => <p key={i}>{i}</p>)}</aside>}
      <div className="toolbar"><label>{t("date")} <select value={selected} onChange={e => setSelected(e.target.value)}>{data.history.map(r => <option key={r.Date} value={r.Date}>{r.Date} · {r.mode === "RESEARCH / EXPERIMENTAL" ? t("research") : language === "ko" && r.mode === "HISTORICAL OOS" ? "과거 OOS" : r.mode}</option>)}</select></label><div className="actions"><button onClick={() => setSelected(data.latest?.Date ?? "")}>{t("latestButton")}</button><button disabled={!data.last_complete} onClick={() => setSelected(data.last_complete?.Date ?? "")}>{t("completeButton")} · {data.last_complete?.Date ?? t("unavailable")}</button><a href="/data/korea-monitor.json" download>{t("download")}</a></div></div>
      <section id="status" className="status-section"><div className="section-title"><h2>{t("overview")}</h2><span>{row?.mode === "RESEARCH / EXPERIMENTAL" ? t("research") : language === "ko" && row?.mode === "HISTORICAL OOS" ? "과거 OOS" : row?.mode ?? t("unavailable")} · {selected}</span></div>
        <div className="metrics"><article><h3>{t("risk")}</h3><strong>{percent(row?.Prob_XGBoost)}</strong><p>{t("riskNote")}</p></article><article><h3>{t("msi")}</h3><strong>{number(row?.Korea_MSI)}</strong><p>{t("msiNote")}</p><small>{t("threshold")}: {number(row?.Stress_Threshold)}</small></article><article><h3>{t("breadthSignal")}</h3><strong>{number(row?.extreme_count, 0)}<small> / 6 {t("extreme")}</small></strong><p>{row?.persistent == null ? t("insufficient") : row?.persistent === 1 ? t("persistent") : t("notPersistent")}</p></article><article className="summary-state"><h3>{t("final")}</h3><strong>{state(row?.state ?? "UNKNOWN / INSUFFICIENT DATA")}</strong><a href="#assessment">{t("inspect")} ↓</a></article></div>
        <div id="assessment" className={`state ${tone(row?.state ?? "UNKNOWN")}`} role="status"><div><span>{t("final")}</span><h2>{state(row?.state ?? "UNKNOWN / INSUFFICIENT DATA")}</h2><p>{language === "ko" ? reasonCopy[row?.reason ?? ""] ?? row?.reason : row?.reason}</p>{row?.state.includes("UNKNOWN") && <><b>{t("missing")}: {[["V1", row?.Prob_XGBoost], ["MSI", row?.Korea_MSI], [t("threshold"), row?.Stress_Threshold], [t("breadthSignal"), row?.persistent]].filter(([, value]) => value == null).map(([label]) => label).join(" · ") || t("insufficient")}</b><p>{t("missingNote")}</p></>}</div><aside><small>{t("complete")}</small><strong>{data.last_complete?.Date ?? t("unavailable")}</strong><p>{t("noCarry")}</p></aside></div>
      </section>
      <div className="two-column"><section id="breadth"><div className="section-title"><h2>{t("breadth")}</h2><span>{t("primary")}</span></div><p>{t("breadthRule")}</p><div className="breadth-summary"><b>{number(row?.window_hits, 0)} / 3 {t("hits")}</b><span>{t("mean")}: {percent(row?.breadth_mean)}</span></div><div className="table-scroll"><table><thead><tr><th>{t("measure")}</th><th>{t("share")}</th><th>{t("percentile")}</th><th>≥90%</th></tr></thead><tbody>{signalCopy.map(([key, en, ko, enDescription, koDescription]) => <tr key={key}><th scope="row">{language === "en" ? en : ko}<small>{language === "en" ? enDescription : koDescription}</small></th><td>{percent(row?.[key])}</td><td>{percent(row?.[`${key}_pct`])}</td><td>{typeof row?.[`${key}_pct`] !== "number" ? t("unknown") : (row[`${key}_pct`] as number) >= .9 ? <span className="flag">{t("extreme")}</span> : "—"}</td></tr>)}</tbody></table></div><p className="footnote">{t("breadthCaveat")}</p></section>
      <section><div className="section-title"><h2>{t("correlation")}</h2><span>{t("confirmOnly")}</span></div><h3 className="confirmation">{corr === null || corr === undefined ? t("unavailable") : corr >= 2 ? t("corrYes") : t("corrNo")}</h3><p>{t("corrRule")}</p><dl><div><dt>{t("corrMean")}</dt><dd>{percent(row?.cross_asset_abs_corr_mean_pct)}</dd></div><div><dt>{t("corrMax")}</dt><dd>{percent(row?.cross_asset_abs_corr_max_pct)}</dd></div><div><dt>{t("extremes")}</dt><dd>{number(corr, 0)} / 2</dd></div><div><dt>{t("sourceDate")}</dt><dd>{data.sources.correlation?.latest ?? t("unavailable")}</dd></div></dl><p>{t("corrNote")}</p><p className="footnote">{t("corrCaveat")}</p></section></div>
      <section><div className="section-title"><div><h2>{t("trend")}</h2><p>{t("through")} {selected}</p></div><label>{t("window")} <select value={window} onChange={e => setWindow(Number(e.target.value))}><option value={60}>60 {t("observations")}</option><option value={120}>120 {t("observations")}</option><option value={252}>252 {t("observations")}</option></select></label></div>
        {chart.length ? <><svg className="chart" viewBox="0 0 1000 230" role="img" aria-label={t("chartLabel")}>{[0, 2, 4, 6].map(n => <g key={n}><line x1="30" x2="990" y1={195 - n * 27} y2={195 - n * 27} stroke={n === 2 ? "#ae8145" : "#e0e3e3"} strokeDasharray={n === 2 ? "4 4" : undefined}/><text x="8" y={199 - n * 27}>{n}</text></g>)}{chart.map((r, i) => r.extreme_count === null ? <text key={r.Date} x={32 + i * 950 / chart.length} y="211">·</text> : <rect key={r.Date} x={32 + i * 950 / chart.length} y={195 - r.extreme_count * 27} width={Math.max(1, 950 / chart.length - 1)} height={Math.max(1, r.extreme_count * 27)} fill={r.persistent === 1 ? "#ae8145" : "#607c85"}><title>{`${r.Date}: ${r.extreme_count}/6 ${t("extreme")}; ${r.persistent === null ? t("unknown") : r.persistent ? t("confirmed") : t("absent")}; ${state(r.state)}` }</title></rect>)}<text x="30" y="229">{chart[0].Date}</text><text x="880" y="229">{chart[chart.length - 1].Date}</text></svg><p className="footnote">{t("legend")}</p></> : <p>{t("unavailable")}</p>}
      </section>
      <section><div className="section-title"><h2>{t("how")}</h2><span>{t("precedence")}</span></div><div className="state-grid">{stateRules.map(([code, en, ko], i) => <article key={code} className={row?.state === code ? "selected-state" : ""}><span className="step-number">{String(i + 1).padStart(2, "0")}</span><h3>{state(code)}</h3><p>{language === "en" ? en : ko}</p></article>)}</div><p className="footnote">{t("allRequire")}</p></section>
      <section id="evidence"><div className="section-title"><h2>{t("evidence")}</h2><span>{t("research")} · 2016-09-13 — 2026-09-16</span></div><div className="evidence-grid">{[[data.evidence.eligible, t("eligible")], [data.evidence.detected, t("detected")], [`${data.evidence.coverage}%`, t("coverage")], [`${data.evidence.median_lead} ${t("days")}`, t("lead")], [`≈${data.evidence.false_warnings_year}`, t("falseWarnings")]].map(([v, label]) => <article key={label}><strong>{v}</strong><p>{label}</p></article>)}</div><p>{t("evidenceNote")}</p></section>
      <section id="holdout"><div className="section-title"><h2>{t("retrospective")}</h2><span>{t("postSelection")}</span></div><h3 className="story-title">{t("story")}</h3><p>{t("storyNote")}</p><div className="timeline"><article><span>2026-10-12</span><h3>{t("initial")}</h3><p>{t("initialText")}</p></article><article><span>2026-10-13</span><h3>{t("activated")}</h3><p>{t("activatedText")}</p></article><article><span>2026-10-14 / 15</span><h3>{t("continued")}</h3><p>{t("continuedText")}</p></article></div><div className="table-scroll"><table><thead><tr><th>{t("date")}</th><th>{t("reportedRisk")}</th><th>{t("reportedReturn")}</th><th>{t("storedBreadth")}</th><th>{t("computed")}</th></tr></thead><tbody>{data.holdout.map(r => <tr key={r.Date}><th>{r.Date}</th><td>{r.reported_v1_percent === undefined ? t("unavailable") : `${r.reported_v1_percent.toFixed(1)}%`}</td><td>{r.reported_return_percent === undefined ? t("unavailable") : `${r.reported_return_percent.toFixed(2)}%`}</td><td>{number(r.extreme_count, 0)} / 6</td><td>{r.persistent === null ? t("unknown") : r.persistent ? t("confirmed") : t("absent")}</td></tr>)}</tbody></table></div><aside className="notice"><b>{t("notPredicted")}</b><p>{t("holdoutNote")}</p></aside></section>
      <section><details><summary>{t("provenance")}</summary><p>{data.dataset}. {t("provenanceNote")}</p>{Object.entries(data.sources).map(([k, s]) => <div className="source" key={k}><b>{k} · {s.rows.toLocaleString()} {t("rows")} · {t("latest")}: {s.latest ?? t("unavailable")}</b><code>{s.path}</code><small>SHA-256: {s.sha256 ?? t("unavailable")}</small></div>)}</details></section>
    </main><footer><span>Market &amp; Portfolio Risk Intelligence</span><span>{t("footer")}</span></footer>
  </div>;
}
