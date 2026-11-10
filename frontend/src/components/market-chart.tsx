"use client";
import { useId, useState } from "react";
import { useDashboard } from "./dashboard-shell";
import { chartRanges, linePath, rangeStart, timestamp, type ChartRange } from "@/lib/chart-data";
import type { MarketPoint } from "@/lib/dashboard-types";

export default function MarketChart({country, points, end}: {country:"us"|"korea"; points:MarketPoint[]; end:string}) {
 const {t,language}=useDashboard();
 const [range,setRange]=useState<ChartRange>("6M");
 const [inspected,setInspected]=useState<string|null>(null);
 const id=useId().replaceAll(":", "");
 const start=rangeStart(end,range,points[0]?.date ?? end);
 const shown=points.filter(p=>timestamp(p.date)>=start && p.date<=end);
 const prices=shown.flatMap(p=>p.price===null ? []:[p.price]);
 const low=prices.length ? Math.min(...prices):0;
 const high=prices.length ? Math.max(...prices):1;
 const pad=Math.max((high-low)*.12,1);
 const min=low-pad,max=high+pad;
 const left=54,right=590,top=18,bottom=166;
 const x=(day:string)=>left+(timestamp(day)-start)/Math.max(1,timestamp(end)-start)*(right-left);
 const y=(value:number)=>bottom-(value-min)/(max-min)*(bottom-top);
 const ry=(value:number)=>bottom-value*(bottom-top);
 const indexPath=linePath(shown,"price",x,y);
 const riskPath=linePath(shown,"risk",x,ry);
 const active=shown.find(p=>p.date===inspected) ?? shown[shown.length-1];
 const latestRisk=points.filter(p=>p.risk!==null && p.date<=end).at(-1)?.date;
 const missingFrom=latestRisk ? Math.max(left,x(latestRisk)) : left;
 const format=(value:number|null|undefined,digits=2)=>typeof value==="number" ? value.toLocaleString(language==="ko"?"ko-KR":"en-US",{minimumFractionDigits:digits,maximumFractionDigits:digits}):"N/A";
 const label=country==="us" ? "SPY" : "KOSPI200";
 return <section className="panel market-chart"><div className="panel-header"><h2>{t(country==="us"?"usChart":"koreaChart")}</h2><div className="range-toggle" role="group" aria-label={t("dateRange")}>{chartRanges.map(item=><button key={item} aria-pressed={item===range} onClick={()=>{setRange(item);setInspected(null);}}>{item}</button>)}</div></div>
  <div className="chart-legend"><span><i className="legend-line navy"/>{label} ({country==="us" ? "USD" : language==="ko"?"포인트":"pts"})</span><span><i className="legend-line red"/>{t("riskRight")}</span><span><i className="legend-dash"/>{t("warningLine")}</span></div>
  {shown.length ? <><svg viewBox="0 0 640 200" role="img" aria-label={`${t(country==="us"?"usChart":"koreaChart")}. ${t("priceLeft")}. ${t("riskRight")}. ${t("gaps")}`} onMouseMove={event=>{
   const rect=event.currentTarget.getBoundingClientRect();
   const px=(event.clientX-rect.left)/rect.width*640;
   const time=start+(px-left)/(right-left)*(timestamp(end)-start);
   const nearest=shown.reduce((a,b)=>Math.abs(timestamp(a.date)-time)<Math.abs(timestamp(b.date)-time)?a:b);
   setInspected(nearest.date);
  }} onMouseLeave={()=>setInspected(null)}>
   <defs><clipPath id={`clip-${id}`}><rect x={left} y={top} width={right-left} height={bottom-top}/></clipPath></defs>
   {[0,.25,.5,.75,1].map(n=><g key={n}><line x1={left} x2={right} y1={top+n*(bottom-top)} y2={top+n*(bottom-top)} stroke="#e8eef5"/><text x={left-10} y={top+n*(bottom-top)+4} textAnchor="end">{Math.round(max-n*(max-min)).toLocaleString("en-US")}</text><text x={right+10} y={top+n*(bottom-top)+4} className="risk-axis">{100-n*100}</text></g>)}
   <g clipPath={`url(#clip-${id})`}><rect x={missingFrom} y={top} width={Math.max(0,right-missingFrom)} height={bottom-top} fill="#edf1f6" opacity=".65"/><line x1={left} x2={right} y1={ry(.5)} y2={ry(.5)} stroke="#df6972" strokeWidth="1" strokeDasharray="5 4"/><path d={indexPath} fill="none" stroke="#173f70" strokeWidth="2" strokeLinejoin="round"/><path d={riskPath} fill="none" stroke="#eb6874" strokeWidth="1.4" strokeLinejoin="round"/>{inspected && active && <line x1={x(active.date)} x2={x(active.date)} y1={top} y2={bottom} stroke="#8195af" strokeDasharray="3 3"/>}</g>
   {[0,.25,.5,.75,1].map(n=>{const date=new Date(start+n*(timestamp(end)-start));return <text key={n} x={left+n*(right-left)} y="191" textAnchor={n===0?"start":n===1?"end":"middle"}>{date.toISOString().slice(0,10)}</text>;})}
  </svg><div className="chart-readout"><time>{active?.date}</time><span>{label} <b>{format(active?.price)}</b></span><span className="risk-readout">V1 <b>{active?.risk==null?"N/A":`${format(active.risk*100,1)}%`}</b></span><span>MSI <b>{format(active?.msi,3)}</b></span></div><label className="chart-slider-label"><span>{t("inspectDate")}</span><input aria-label={`${label} ${t("inspectDate")}`} type="range" min="0" max={shown.length-1} value={Math.max(0,shown.findIndex(p=>p.date===active?.date))} onChange={event=>setInspected(shown[Number(event.target.value)].date)}/></label></> : <div className="chart-empty">{t("noSeries")}</div>}
  <div className="chart-caption"><span><i className="legend-square"/>{t("noRisk")}</span><span>{t("historicalOos")} → {latestRisk ?? "N/A"}</span></div><p className="panel-note">{t("gaps")}</p>
 </section>;
}
