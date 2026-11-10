"use client";
import Link from "next/link";
import { currentOperationalPoint, operationalMessage } from "@/lib/operational-status";
import CountryFlag from "./country-flag";
import { useState } from "react";
import { useDashboard } from "./dashboard-shell";
import { signalCopy, stateCopy, stateRules, reasonCopy } from "@/lib/monitor-copy";
import type { MonitorData } from "@/lib/dashboard-types";
type Row = MonitorData["history"][number];
const pct=(value:unknown)=>typeof value==="number"?`${(value*100).toFixed(1)}%`:"N/A";
const num=(value:unknown,digits=3)=>typeof value==="number"?value.toFixed(digits):"N/A";

export function CountryCards({only}:{only?:"us"|"korea"}) {
 const {t,global,monitor,language,operational}=useDashboard();
 const asOf=global?.asOf ?? monitor?.latest?.Date;
 return <div className={`country-grid ${only ? "single" : ""}`}>{(["us","korea"] as const).filter(c=>!only||c===only).map(country=>{
  const points=country==="us"?global?.us:global?.korea;
  const latestSource=points?.filter(p=>p.price!==null||p.msi!==null||p.risk!==null).at(-1);
  const current=points?.find(p=>p.date===asOf);
  const oos=points?.filter(p=>p.risk!==null).at(-1);
  const operation=operational?.markets[country];
  const operatingPoint=currentOperationalPoint(operation);
  const monitoringState=!operation&&country==="korea"?monitor?.latest?.state:undefined;
  const complete=country==="korea"?monitor?.last_complete?.Date:oos?.date;
  const risk=operation?operatingPoint?.risk:country==="korea"?monitor?.latest?.Prob_XGBoost:current?.risk;
  const msi=operation?operatingPoint?.msi:country==="korea"?monitor?.latest?.Korea_MSI:current?.msi;
  return <section className="panel country-card" key={country}><div className="panel-header"><Link href={`/${country}`} className="country-title"><CountryFlag country={country}/><h2>{t(country)}</h2><span aria-hidden="true">›</span></Link><span className="source-date">{t(operation?"operationalAsOf":"sourceAsOf")}<b>{(operation?operation.expectedDate:country==="korea"?monitor?.latest?.Date:latestSource?.date) ?? "N/A"}</b></span></div><div className="country-metrics"><div className="country-metric"><h3>{t("risk10")}</h3><strong>{pct(risk)}</strong><p>{t("futureRisk")}</p></div><div className="country-metric"><h3>MSI</h3><strong>{num(msi)}</strong><p>{t("currentStress")}</p></div><div className="country-status"><span className="status-label"><i/>{operation?(operatingPoint?(language==="ko"?"필수 관측 확인":"Inputs verified"):(language==="ko"?"최신 점수 미확인":"Current score unavailable")):monitoringState?stateCopy[monitoringState]?.[language==="en"?0:1]??monitoringState:t("unknownState")}</span><p>{operation?operationalMessage(operation,language):monitoringState&&!monitoringState.includes("UNKNOWN")?(language==="ko"?reasonCopy[monitor?.latest?.reason??""]??monitor?.latest?.reason:monitor?.latest?.reason):t("currentNote")}</p><Link href={`/${country}`}>{t("openMarket")} →</Link></div></div><div className="country-meta"><span>{t("oosAsOf")} <b>{oos?.date ?? "N/A"}</b></span><span>{t("complete")} <b>{complete ?? "N/A"}</b></span></div><span className="country-scope">{t(country==="us"?"originalV1":"experimentalKorea")}</span>{language==="ko" && <span className="sr-only">{t("notLive")}</span>}</section>;
 })}</div>;
}

export function BreadthPanel({row,compact=false}:{row?:Row|null;compact?:boolean}) {
 const {t,language,monitor}=useDashboard();
 const value=row === undefined?monitor?.latest:row;
 const [mode,setMode]=useState<"share"|"percentile">("percentile");
 return <section className="panel breadth-panel"><div className="panel-header"><h2>{t("breadthPanel")}</h2><span className="tag">{t("onlyKorea")}</span></div><div className="panel-subheader"><time>{value?.Date ?? "N/A"}</time><div className="small-toggle" role="group" aria-label={t("breadthPanel")}><button aria-pressed={mode==="share"} onClick={()=>setMode("share")}>{t("stockShare")}</button><button aria-pressed={mode==="percentile"} onClick={()=>setMode("percentile")}>{t("percentileBars")}</button></div></div><div className="breadth-bars">{signalCopy.map(([key,en,ko,enDescription,koDescription])=>{
  const v=value?.[mode==="share"?key:`${key}_pct`];
  const extreme=typeof value?.[`${key}_pct`]==="number" && (value[`${key}_pct`] as number)>=.9;
  return <div className="breadth-row" key={key}><span title={language==="en"?enDescription:koDescription}>{language==="en"?en:ko}</span><div className={`bar-track ${extreme?"extreme":""}`} role="img" aria-label={`${language==="en"?en:ko}: ${pct(v)}`}><span style={{width:typeof v==="number"?`${v*100}%`:"0%"}}/>{mode==="percentile"&&<i className="percentile-cutoff"/>}</div><b>{pct(v)}</b></div>;
 })}</div><div className="breadth-facts"><span>{t("extremes")} <b>{num(value?.extreme_count,0)} / 6</b></span><span>{t("hits")} <b>{num(value?.window_hits,0)} / 3</b></span></div><p className="panel-note">{t("primary")} · {value?.persistent==null?t("insufficient"):value.persistent===1?t("persistent"):t("notPersistent")}</p>{!compact&&<><p>{t("breadthRule")}</p><p className="panel-note">{t("breadthCaveat")}</p></>}</section>;
}

export function CorrelationPanel({full=false}:{full?:boolean}) {
 const {t,global}=useDashboard();
 const [selected,setSelected]=useState(global?.correlation.at(-1)?.date ?? "");
 const row=global?.correlation.find(r=>r.date===selected);
 const assets=["KOSPI200","SPY","TLT","GLD"];
 const pairs=[[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]];
 return <section className="panel correlation-panel"><div className="panel-header"><h2>{t("heatmap")}</h2><span className="tag">{t("confirmOnly")}</span></div><div className="panel-subheader"><span>{t(full?"date":"lastStored")}</span><time>{row?.date??"N/A"}</time></div>{row?<div className="heatmap-wrap"><table className="heatmap"><thead><tr><th aria-label={t("correlation")}/>{assets.map(a=><th key={a}>{a}</th>)}</tr></thead><tbody>{assets.map((asset,i)=><tr key={asset}><th scope="row">{asset}</th>{assets.map((other,j)=>{
  const position=pairs.findIndex(([a,b])=>(a===i&&b===j)||(a===j&&b===i));
  const value=row.values[position];
  return <td key={other} style={{background:i===j?"#edf3f9":typeof value==="number"?value>=0?`rgba(37,99,166,${.08+Math.abs(value)*.65})`:`rgba(236,105,118,${.08+Math.abs(value)*.55})`:"#f2f5f8",color:typeof value==="number"&&value>.65?"white":undefined}}>{i===j?"—":num(value,2)}</td>;
 })}</tr>)}</tbody></table><div className="heatmap-scale"><span>−1</span><i/><span>+1</span></div></div>:<div className="empty-state">{t("unavailable")}</div>}<p className="panel-note">{t("heatmapWindow")} · {t("notCurrent")}</p>{full&&row&&<label className="field-label">{t("date")}<select value={selected} onChange={e=>setSelected(e.target.value)}>{global?.correlation.map(r=><option key={r.date}>{r.date}</option>)}</select></label>}<p className="panel-note">{t("heatmapNote")}</p></section>;
}

export function PerformancePanel() {
 const {t,global}=useDashboard();
 return <section className="panel performance-panel"><div className="panel-header"><h2>{t("performance")}</h2><span className="tag">{t("us")}</span></div><p className="scope-label">{t("originalV1")}</p>{global?.usMetrics.length?<div className="table-scroll"><table><thead><tr><th>{t("horizon")}</th><th>ROC-AUC</th><th>{t("precision")}</th><th>{t("recall")}</th><th>F1</th></tr></thead><tbody>{global.usMetrics.map(m=><tr key={m.horizon}><th scope="row" title={`${m.start} — ${m.end}; n=${m.n}`}>{m.horizon}</th><td>{m.auc.toFixed(3)}</td><td>{m.precision.toFixed(3)}</td><td>{m.recall.toFixed(3)}</td><td>{m.f1.toFixed(3)}</td></tr>)}</tbody></table></div>:<div className="empty-state">{t("noUsValidation")}</div>}<p className="panel-note">{t("storedMetrics")}</p><Link className="text-link" href="/validation">{t("expand")} →</Link></section>;
}

export function ValidationPanel() {
 const {t,monitor}=useDashboard();
 const evidence=monitor?.evidence;
 return <section className="panel validation-panel"><div className="panel-header"><h2>{t("evidence")} · {t("korea")}</h2><span className="tag">{t("research")}</span></div><p className="scope-label">2016-09-13 — 2026-09-16 · {t("experimentalKorea")}</p><div className="validation-kpis">{[[evidence?.eligible,t("eligible")],[evidence?.detected,t("detected")],[evidence?`${evidence.coverage}%`:"N/A",t("coverage")],[evidence?.median_lead,`${t("lead")} (${t("days")})`],[evidence?`≈${evidence.false_warnings_year}`:"N/A",t("falseWarnings")]].map(([v,label])=><article key={label}><strong>{v??"N/A"}</strong><span>{label}</span></article>)}</div><p className="panel-note">{t("evidenceNote")}</p></section>;
}

export function TimelinePanel({full=false}:{full?:boolean}) {
 const {t,monitor}=useDashboard();
 const events=[{date:"2026-10-12",title:"initial",text:"initialText"},{date:"2026-10-13",title:"activated",text:"activatedText"},{date:"2026-10-14",title:"continued",text:"continuedText"},{date:"2026-10-15",title:"continued",text:"continuedText"}] as const;
 return <section className={`panel timeline-panel ${full?"full":""}`}><div className="panel-header"><h2>{t("retrospective")} · {t("korea")}</h2>{!full?<Link className="text-link" href="/cases">{t("allCases")} →</Link>:<span className="tag">{t("postSelection")}</span>}</div><p className="scope-label timeline-metric-label">{t("reportedReturn")} · {t("reportedRisk")}</p><div className="event-timeline">{events.map((event,i)=>{
  const row=monitor?.holdout.find(r=>r.Date===event.date);
  return <article key={event.date} className={i===1?"active-event":""}><span className="timeline-node"/><time>{event.date.slice(5).replace("-",".")}</time><h3>{t(event.title)}</h3><strong className="event-return">{row?.reported_return_percent===undefined?"N/A":`${row.reported_return_percent.toFixed(2)}%`}</strong><span>V1 {row?.reported_v1_percent===undefined?"N/A":`${row.reported_v1_percent.toFixed(1)}%`} <small>{t("research")}</small></span>{full&&<p>{t(event.text)}</p>}</article>;
 })}</div><p className="timeline-disclaimer">{t("notPredicted")}</p>{full&&<><p>{t("holdoutNote")}</p><div className="table-scroll"><table><thead><tr><th>{t("date")}</th><th>{t("reportedRisk")}</th><th>{t("reportedReturn")}</th><th>{t("storedBreadth")}</th><th>{t("computed")}</th></tr></thead><tbody>{monitor?.holdout.map(row=><tr key={row.Date}><th scope="row">{row.Date}</th><td>{row.reported_v1_percent===undefined?"N/A":`${row.reported_v1_percent.toFixed(1)}%`}</td><td>{row.reported_return_percent===undefined?"N/A":`${row.reported_return_percent.toFixed(2)}%`}</td><td>{num(row.extreme_count,0)} / 6</td><td>{row.persistent===null?t("unknown"):row.persistent?t("confirmed"):t("absent")}</td></tr>)}</tbody></table></div></>}</section>;
}

export function InsightsPanel() {
 const {t}=useDashboard();
 return <section className="panel insights-panel"><div className="panel-header"><h2>{t("insights")}</h2><Link className="text-link" href="/methodology">{t("methodology")} →</Link></div>{([1,2,3] as const).map((n)=><article key={n}><span>{n}</span><div><h3>{t(`insight${n}`)}</h3><p>{t(`insight${n}Text`)}</p></div></article>)}</section>;
}

export function MonitoringState({row}:{row:Row|null}) {
 const {t,language,monitor}=useDashboard();
 const state=row?.state??"UNKNOWN / INSUFFICIENT DATA";
 const missing=[["V1",row?.Prob_XGBoost],["MSI",row?.Korea_MSI],[t("threshold"),row?.Stress_Threshold],[t("breadthSignal"),row?.persistent]].filter(([,v])=>v==null).map(([name])=>name);
 return <section className={`panel monitoring-state ${state.includes("UNKNOWN")?"unknown":state==="NORMAL"?"normal":"caution"}`} aria-live="polite"><div><span className="scope-label">{t("final")} · {row?.Date??"N/A"}</span><h2>{stateCopy[state]?.[language==="en"?0:1]??state}</h2><code>{state}</code><p>{language==="ko"?reasonCopy[row?.reason??""]??row?.reason:row?.reason}</p>{state.includes("UNKNOWN")&&<><b>{t("missing")}: {missing.join(" · ")||t("insufficient")}</b><p className="panel-note">{t("missingNote")}</p></>}</div><aside><small>{t("complete")}</small><strong>{monitor?.last_complete?.Date??"N/A"}</strong><p>{t("noCarry")}</p></aside></section>;
}

export function StateRulesPanel() {
 const {t,language}=useDashboard();
 return <section className="panel"><div className="panel-header"><h2>{t("how")}</h2><span className="tag">{t("research")}</span></div><p>{t("precedence")}</p><div className="rule-grid">{stateRules.map(([code,en,ko],i)=><article key={code}><span>{String(i+1).padStart(2,"0")}</span><div><h3>{stateCopy[code]?.[language==="en"?0:1]??code}</h3><p>{language==="en"?en:ko}</p></div></article>)}</div><p className="panel-note">{t("allRequire")}</p></section>;
}

export function BreadthTrend() {
 const {t,monitor,language}=useDashboard();
 const [count,setCount]=useState(120);
 const chart=monitor?.history.slice(-count)??[];
 return <section className="panel"><div className="panel-header"><h2>{t("trend")}</h2><select aria-label={t("window")} value={count} onChange={e=>setCount(Number(e.target.value))}>{[60,120,252].map(n=><option key={n} value={n}>{n} {t("observations")}</option>)}</select></div>{chart.length?<svg className="breadth-chart" viewBox="0 0 1000 210" role="img" aria-label={t("chartLabel")}>{[0,2,4,6].map(n=><g key={n}><line x1="28" x2="990" y1={175-n*25} y2={175-n*25} stroke={n===2?"#ad8751":"#e7edf5"} strokeDasharray={n===2?"4 4":undefined}/><text x="5" y={179-n*25}>{n}</text></g>)}{chart.map((r,i)=>r.extreme_count===null?null:<rect key={r.Date} x={30+i*960/chart.length} y={175-r.extreme_count*25} width={Math.max(1,960/chart.length-1)} height={Math.max(1,r.extreme_count*25)} fill={r.persistent===1?"#b1884e":"#748fae"}><title>{`${r.Date} · ${r.extreme_count}/6 · ${stateCopy[r.state]?.[language==="en"?0:1]??r.state}`}</title></rect>)}<text x="28" y="202">{chart[0].Date}</text><text x="990" y="202" textAnchor="end">{chart.at(-1)?.Date}</text></svg>:<p>{t("unavailable")}</p>}<p className="panel-note">{t("legend")}</p></section>;
}

export function SourcesPanel() {
 const {t,monitor,global}=useDashboard();
 const sources=[...Object.entries(monitor?.sources??{}).map(([name,s])=>({name,...s,project:t("experimentalKorea")})),...Object.entries(global?.sources??{}).map(([name,s])=>({name,...s,project:s.project.startsWith("Original")?t("originalV1"):t("experimentalKorea")}))];
 return <><section className="panel"><div className="panel-header"><h2>{t("sources")}</h2><span className="tag">{t("snapshot")}</span></div><p>{t("dataIntro")}</p><div className="source-actions"><a className="button-link" href="/data/korea-monitor.json" download>{t("download")}</a><a className="button-link" href="/data/global-markets.json" download>{t("downloadGlobal")}</a></div><div className="table-scroll"><table className="source-table"><thead><tr><th>{t("source")}</th><th>{t("project")}</th><th>{t("rows")}</th><th>{t("latest")}</th></tr></thead><tbody>{sources.map((s,i)=><tr key={`${s.name}-${i}`}><th scope="row">{s.name}<code>{s.path}</code></th><td>{s.project}</td><td>{s.rows.toLocaleString("en-US")}</td><td>{s.latest??"N/A"}</td></tr>)}</tbody></table></div><p>{t("provenanceNote")}</p><p className="panel-note">{t("sourceText")}</p><details><summary>{t("fingerprints")}</summary>{sources.map((s,i)=><div className="fingerprint" key={`${s.name}-${i}`}><b>{s.name}</b><code>{s.sha256??"N/A"}</code></div>)}</details>{[...(monitor?.issues??[]),...(global?.issues??[])].map(issue=><p className="source-diagnostic" key={issue} lang="en">{issue}</p>)}</section></>;
}
