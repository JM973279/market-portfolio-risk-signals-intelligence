"use client";
import { useId, useMemo, useState } from "react";
import { useDashboard } from "./dashboard-shell";
import { marketOrder } from "@/lib/market-order";
import { HORIZON, byYear, counts, episodes, forwardLabels, oosSpan, rocAuc } from "@/lib/backtest";
import { timestamp } from "@/lib/chart-data";
import type { MarketPoint } from "@/lib/dashboard-types";

const ranges = ["ALL", "5Y", "2Y", "1Y"] as const;
type Range = typeof ranges[number];
const pct = (v: number | null | undefined, d = 1) => typeof v === "number" ? `${(v * 100).toFixed(d)}%` : "—";

export default function BacktestPanel() {
 const { t, language, global } = useDashboard();
 const [market, setMarket] = useState<"us" | "korea" | null>(null);
 const shownMarket = market ?? marketOrder(language)[0];
 const points = useMemo(() => ((shownMarket === "us" ? global?.us : global?.korea) ?? []), [global, shownMarket]);
 const [cut, setCut] = useState(50);
 const c = cut / 100;
 const labels = useMemo(() => forwardLabels(points, HORIZON), [points]);
 const auc = useMemo(() => rocAuc(points, labels), [points, labels]);
 const span = useMemo(() => oosSpan(points, labels), [points, labels]);
 const total = useMemo(() => counts(points, labels, c), [points, labels, c]);
 const years = useMemo(() => byYear(points, labels, c), [points, labels, c]);
 const events = useMemo(() => episodes(points, c), [points, c]);
 const reported = shownMarket === "us" ? global?.usMetrics.find(m => m.horizon === "10D") : undefined;
 const matches = !!reported && cut === 50 && total.n === reported.n && Math.abs((total.precision ?? 0) - reported.precision) < 1e-9 && Math.abs((total.recall ?? 0) - reported.recall) < 1e-9;
 const warned = events.filter(e => e.verdict === "warned");
 const leads = warned.map(e => e.lead as number).sort((a, b) => a - b);
 const medianLead = leads.length ? leads[Math.floor(leads.length / 2)] : null;
 const [showAll, setShowAll] = useState(false);
 const [missedOnly, setMissedOnly] = useState(false);
 const listed = events.filter(e => !missedOnly || e.verdict === "missed").slice().reverse();
 const rows = showAll ? listed : listed.slice(0, 12);
 const leadText = (lead: number | null) => lead === null ? "—" : `${lead >= HORIZON ? `${HORIZON}+` : lead} ${t("btBefore")}`;
 if (!points.length || !span) return <section className="panel backtest-panel"><h2>{t("btTitle")}</h2><p>{t("btUnavailable")}</p></section>;
 return <section className="panel backtest-panel">
  <div className="panel-header"><h2>{t("btTitle")}</h2><span className="tag">{t("btTag")}</span></div>
  <div className="backtest-controls">
   <div className="small-toggle" role="group" aria-label={t("btMarket")}>{marketOrder(language).map(m => <button key={m} aria-pressed={shownMarket === m} onClick={() => { setMarket(m); setShowAll(false); }}>{t(m)}</button>)}</div>
   <label className="backtest-cut"><span>{t("btCut")} <b>{cut}%</b></span><input type="range" min="30" max="70" step="5" value={cut} onChange={e => setCut(Number(e.target.value))} aria-label={t("btCut")}/>{cut !== 50 && <button onClick={() => setCut(50)}>{t("btReset")}</button>}</label>
  </div>
  <p className="scope-label">{t(shownMarket === "us" ? "btScopeUs" : "btScopeKorea")} · {span.first} — {span.last} · n={total.n.toLocaleString("en-US")}</p>
  <div className="backtest-kpis">
   <article><strong>{total.warnings.toLocaleString("en-US")}</strong><span>{t("btWarnings")}</span></article>
   <article><strong>{pct(total.precision)}</strong><span>{t("btPrecision")}</span></article>
   <article><strong>{pct(total.recall)}</strong><span>{t("btRecall")}</span></article>
   <article><strong>{total.f1 === null ? "—" : total.f1.toFixed(3)}</strong><span>{t("btF1")}</span></article>
   <article><strong>{auc === null ? "—" : auc.toFixed(3)}</strong><span>{t("btAuc")}</span></article>
  </div>
  <p className={`backtest-badge ${matches ? "ok" : ""}`}>{shownMarket === "korea" ? t("btNoReported") : cut === 50 ? (matches ? `✓ ${t("btMatch")}` : "—") : t("btCutNote")}</p>
  <div className="backtest-grid">
   <div><h3>{t("btMatrix")} · {cut}%</h3><div className="confusion" role="table" aria-label={t("btMatrix")}>
    <div className="cell tp" role="row"><span>{t("btTp")}</span><b>{total.tp.toLocaleString("en-US")}</b><small>{t("btDays")}</small></div>
    <div className="cell fp" role="row"><span>{t("btFp")}</span><b>{total.fp.toLocaleString("en-US")}</b><small>{t("btDays")}</small></div>
    <div className="cell fn" role="row"><span>{t("btFn")}</span><b>{total.fn.toLocaleString("en-US")}</b><small>{t("btDays")}</small></div>
    <div className="cell tn" role="row"><span>{t("btTn")}</span><b>{total.tn.toLocaleString("en-US")}</b><small>{t("btDays")}</small></div>
   </div><p className="panel-note">{t("btLabelRule")}</p></div>
   <BacktestChart points={points} cut={c} events={events} last={span.last} label={shownMarket === "us" ? "SPY (USD)" : "KOSPI200"}/>
  </div>
  <div className="backtest-grid lower">
   <div><h3>{t("btYears")}</h3><div className="table-scroll backtest-years"><table><thead><tr><th>{t("btYear")}</th><th>{t("btObs")}</th><th>{t("btAhead")}</th><th>{t("btWarnings")}</th><th>{t("btPrecision")}</th><th>{t("btRecall")}</th></tr></thead><tbody>{years.slice().reverse().map(y => <tr key={y.year}><th scope="row">{y.year}</th><td>{y.n}</td><td>{y.positives}</td><td>{y.warnings}</td><td>{pct(y.precision, 0)}</td><td className={y.recall !== null && y.recall < .5 ? "weak" : undefined}>{pct(y.recall, 0)}</td></tr>)}</tbody></table></div><p className="panel-note">{t("btYearNote")}</p></div>
   <div><div className="backtest-events-head"><h3>{t("btEvents")}</h3><p><b>{events.length}</b> {t("btSummary")} <b>{warned.length}</b> · {t("btMedianLead")} <b>{leadText(medianLead)}</b></p></div>
    <div className="small-toggle" role="group" aria-label={t("btEvents")}><button aria-pressed={!missedOnly} onClick={() => setMissedOnly(false)}>{t("scenarioAll")}</button><button aria-pressed={missedOnly} onClick={() => setMissedOnly(true)}>{t("btMissedOnly")}</button></div>
    <div className="table-scroll"><table className="backtest-events"><thead><tr><th>{t("btOnset")}</th><th>{t("btEnd")}</th><th>{t("btStressDays")}</th><th>{t("btVerdict")}</th><th>{t("btLead")}</th><th>{t("btPrior")}</th><th>{t("btPeak")}</th></tr></thead><tbody>{rows.map(e => <tr key={e.onset}><th scope="row">{e.onset}</th><td>{e.end}</td><td>{e.stressDays}</td><td><span className={`verdict ${e.verdict}`}>{t(e.verdict === "warned" ? "btWarned" : e.verdict === "missed" ? "btMissed" : "btNoData")}</span></td><td>{leadText(e.lead)}</td><td>{pct(e.priorRisk)}</td><td>{e.peakMsi === null ? "—" : e.peakMsi.toFixed(2)}</td></tr>)}</tbody></table></div>
    {listed.length > 12 && <button className="backtest-more" onClick={() => setShowAll(!showAll)}>{t(showAll ? "btShowRecent" : "btShowAll")} ({listed.length})</button>}
    <p className="panel-note">{t("btEventRule")}</p></div>
  </div>
  <p className="panel-note">{t("btCaveat")}{shownMarket === "korea" && <> {t("btKoreaCaveat")}</>}</p>
 </section>;
}

function BacktestChart({ points, cut, events, last, label }: { points: MarketPoint[]; cut: number; events: ReturnType<typeof episodes>; last: string; label: string }) {
 const { t, language } = useDashboard();
 const [range, setRange] = useState<Range>("ALL");
 const [inspected, setInspected] = useState<string | null>(null);
 const id = useId().replaceAll(":", "");
 const endT = timestamp(last);
 const firstT = timestamp(points[0].date);
 const startT = range === "ALL" ? firstT : Math.max(firstT, endT - Number(range[0]) * 365.25 * 86400000);
 const shown = points.filter(p => { const v = timestamp(p.date); return v >= startT && v <= endT; });
 const prices = shown.flatMap(p => p.price === null ? [] : [p.price]);
 const lo = prices.length ? Math.min(...prices) : 0, hi = prices.length ? Math.max(...prices) : 1;
 const pad = Math.max((hi - lo) * .08, 1), min = Math.max(0, lo - pad), max = hi + pad;
 const L = 52, R = 600, T = 14, B = 176;
 const x = (d: string) => L + (timestamp(d) - startT) / Math.max(1, endT - startT) * (R - L);
 const y = (v: number) => B - (v - min) / (max - min) * (B - T);
 const ry = (v: number) => B - v * (B - T);
 const path = (key: "price" | "risk", f: (v: number) => number) => { let on = false; return shown.map(p => { const v = p[key]; if (v === null || !Number.isFinite(v)) { on = false; return ""; } const s = `${on ? "L" : "M"}${x(p.date).toFixed(1)},${f(v).toFixed(1)}`; on = true; return s; }).join(" "); };
 const active = shown.find(p => p.date === inspected) ?? shown.at(-1);
 const yearsTicks = Array.from(new Set(shown.map(p => p.date.slice(0, 4)))).filter((_, i, a) => a.length <= 8 || i % Math.ceil(a.length / 8) === 0);
 const fmt = (v: number | null | undefined, d = 2) => typeof v === "number" ? v.toLocaleString(language === "ko" ? "ko-KR" : "en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "N/A";
 return <div className="backtest-chart"><div className="backtest-chart-head"><h3>{t("btChart")}</h3><div className="range-toggle" role="group" aria-label={t("dateRange")}>{ranges.map(r => <button key={r} aria-pressed={r === range} onClick={() => { setRange(r); setInspected(null); }}>{r}</button>)}</div></div>
  <div className="chart-legend"><span><i className="legend-line navy"/>{label} · {t("priceLeft")}</span><span><i className="legend-line red"/>{t("btRisk")}</span><span><i className="legend-dash"/>{t("btCut")} {Math.round(cut * 100)}%</span><span><i className="legend-band"/>{t("btBand")}</span></div>
  <svg viewBox="0 0 640 200" role="img" aria-label={`${t("btChart")}. ${t("btBand")}`} onMouseMove={ev => { const r = ev.currentTarget.getBoundingClientRect(); const px = (ev.clientX - r.left) / r.width * 640; const tm = startT + (px - L) / (R - L) * (endT - startT); const near = shown.reduce((a, b) => Math.abs(timestamp(a.date) - tm) < Math.abs(timestamp(b.date) - tm) ? a : b); setInspected(near.date); }} onMouseLeave={() => setInspected(null)}>
   <defs><clipPath id={`bt-${id}`}><rect x={L} y={T} width={R - L} height={B - T}/></clipPath></defs>
   {[0, .25, .5, .75, 1].map(n => <g key={n}><line x1={L} x2={R} y1={T + n * (B - T)} y2={T + n * (B - T)} stroke="#e8eef5"/><text x={L - 8} y={T + n * (B - T) + 4} textAnchor="end">{Math.round(max - n * (max - min)).toLocaleString("en-US")}</text><text x={R + 8} y={T + n * (B - T) + 4} className="risk-axis">{100 - n * 100}</text></g>)}
   <g clipPath={`url(#bt-${id})`}>
    {events.map(e => <rect key={e.onset} x={x(e.onset)} y={T} width={Math.max(1.5, x(e.end) - x(e.onset))} height={B - T} fill="#e86371" opacity=".16"><title>{`${e.onset} — ${e.end}`}</title></rect>)}
    <line x1={L} x2={R} y1={ry(cut)} y2={ry(cut)} stroke="#df6972" strokeDasharray="5 4"/>
    <path d={path("price", y)} fill="none" stroke="#173f70" strokeWidth="1.6"/>
    <path d={path("risk", ry)} fill="none" stroke="#eb6874" strokeWidth="1" opacity=".85"/>
    {inspected && active && <line x1={x(active.date)} x2={x(active.date)} y1={T} y2={B} stroke="#8195af" strokeDasharray="3 3"/>}
   </g>
   {yearsTicks.map(yr => { const d = shown.find(p => p.date.startsWith(yr))!.date; return <text key={yr} x={x(d)} y="194" textAnchor="middle">{yr}</text>; })}
  </svg>
  <div className="chart-readout"><time>{active?.date}</time><span>{label.split(" ")[0]} <b>{fmt(active?.price)}</b></span><span className="risk-readout">V1 <b>{active?.risk == null ? "N/A" : `${fmt(active.risk * 100, 1)}%`}</b></span><span>MSI <b>{fmt(active?.msi, 3)}</b></span></div>
 </div>;
}
