"use client";
import { useDashboard } from "@/components/dashboard-shell";
import { MAX_HOLDINGS, inputProblem, weightTotal, type Analysis, type Asset, type Comparison, type Factor, type FactorBeta, type FactorSignificance, type Holding, type Scenarios } from "@/lib/portfolio-api";
import { apiTextEn, portfolioCopy, type PortfolioCopyKey } from "@/lib/portfolio-copy";
import styles from "./portfolio.module.css";

export function usePortfolioCopy() {
 const { language } = useDashboard();
 return (key: PortfolioCopyKey) => portfolioCopy[key][language === "en" ? 0 : 1];
}

function useFormat() {
 const { language } = useDashboard();
 const locale = language === "ko" ? "ko-KR" : "en-US";
 const num = (v: number, digits = 1) => Math.abs(v).toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
 const sign = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "");
 return {
  pct: (v: number, digits = 1) => `${v < 0 ? "−" : ""}${num(v, digits)}%`,
  signedPct: (v: number, digits = 1) => `${sign(v)}${num(v, digits)}%`,
  pp: (v: number, digits = 1) => `${sign(v)}${num(v, digits)}%p`,
  usd: (v: number) => `${v < 0 ? "−" : ""}$${num(v, 0)}`,
  signedUsd: (v: number) => `${sign(v)}$${num(v, 0)}`,
  beta: (v: number) => `${v < 0 ? "−" : ""}${num(v, 2)}`,
  signedBeta: (v: number) => `${sign(v)}${num(v, 2)}`,
 };
}

// Diverging scale for correlations: blue (−1) → neutral → red (+1).
function mix(from: number[], to: number[], t: number) {
 return `rgb(${from.map((c, i) => Math.round(c + (to[i] - c) * t)).join(",")})`;
}
const NEUTRAL = [243, 246, 250], RED = [232, 99, 113], BLUE = [37, 99, 166];
const corrColor = (c: number) => mix(NEUTRAL, c >= 0 ? RED : BLUE, Math.min(1, Math.abs(c)));

const FACTORS: Factor[] = ["market", "rate", "volatility"];

// Betas that are not distinguishable from zero (|t| below the API threshold) are faded; hover shows t.
function FactorCells({ row, bold }: { row: FactorBeta & FactorSignificance; bold?: boolean }) {
 const { beta, signedPct } = useFormat();
 const text: Record<Factor, string> = { market: beta(row.market), rate: signedPct(row.rate * 1e4, 2), volatility: signedPct(row.volatility * 1e3, 2) };
 return <>{FACTORS.map(f => {
  const t = row.t_stat?.[f];
  return <td key={f} className={row.significant?.[f] === false ? styles.faded : ""} title={t == null ? undefined : `t = ${t.toFixed(2)}`}>{bold ? <b>{text[f]}</b> : text[f]}</td>;
 })}</>;
}

// `label` names the editor (current / changed) so the two editors' fields have distinct accessible names.
export function HoldingsEditor({ label, holdings, onChange, assets, value }: { label: string; holdings: Holding[]; onChange: (next: Holding[]) => void; assets: Asset[]; value: number }) {
 const p = usePortfolioCopy();
 const { pct } = useFormat();
 const total = weightTotal(holdings);
 const problem = inputProblem(holdings, value);
 const update = (index: number, patch: Partial<Holding>) => onChange(holdings.map((h, i) => (i === index ? { ...h, ...patch } : h)));
 return <>
  <div className="table-scroll"><table className={styles.editor}><thead><tr><th>{p("asset")}</th><th>{p("weight")}</th><th><span className="sr-only">{p("remove")}</span></th></tr></thead><tbody>
   {holdings.map((h, i) => <tr key={i}>
    <th scope="row"><select aria-label={`${label} ${p("asset")} ${i + 1}`} value={h.ticker} onChange={e => update(i, { ticker: e.target.value })}><option value="">{p("choose")}</option>{assets.map(a => <option key={a.ticker} value={a.ticker}>{a.ticker} · {a.name}</option>)}</select></th>
    <td><input aria-label={`${label} ${p("weight")} ${i + 1}`} type="number" inputMode="decimal" min="0" max="100" step="0.01" value={Number.isFinite(h.weight) ? h.weight : ""} onChange={e => update(i, { weight: e.target.value === "" ? NaN : Number(e.target.value) })}/></td>
    <td><button type="button" className={styles.removeButton} aria-label={`${label} ${h.ticker || i + 1} ${p("remove")}`} disabled={holdings.length === 1} onClick={() => onChange(holdings.filter((_, j) => j !== i))}>{p("remove")}</button></td>
   </tr>)}
  </tbody></table></div>
  <div className={styles.editorFooter}>
   <button type="button" disabled={holdings.length >= MAX_HOLDINGS} onClick={() => onChange([...holdings, { ticker: "", weight: NaN }])}>{p("addAsset")}</button>
   <span className={`${styles.total} ${Math.abs(total - 100) > 0.01 ? styles.totalBad : ""}`}>{p("total")}<b>{pct(total, 2)}</b></span>
  </div>
  {problem && problem !== "value" && <p className={styles.problem} role="status">{p(problem)}</p>}
 </>;
}

export function HiddenRiskMap({ analysis }: { analysis: Analysis }) {
 const p = usePortfolioCopy();
 const { pct, pp, beta } = useFormat();
 const english = useDashboard().language === "en";
 const sectorNote = english ? [apiTextEn.sectorLabel, ...apiTextEn.sectorLimitations] : [analysis.sector_methodology.label, ...analysis.sector_methodology.limitations];
 const risk = new Map(analysis.risk_contribution.map(r => [r.ticker, r.share]));
 const scale = Math.max(...analysis.allocation.map(a => Math.max(a.weight, risk.get(a.ticker) ?? 0)), 1);
 const exposure = analysis.factor_exposure;
 const { tickers, matrix } = analysis.correlation;
 return <>
  <div className={styles.sectionTitle}><span className={styles.step}>STEP 3</span><h2>{p("hiddenTitle")}</h2></div>
  <div className="selected-metrics">
   <div><span>{p("volatility")}</span><strong>{pct(analysis.volatility, 1)}</strong></div>
   <div><span>{p("maxAsset")} · {analysis.concentration.max_asset.ticker}</span><strong>{pct(analysis.concentration.max_asset.weight, 1)}</strong></div>
   <div><span>{p("maxSector")} · {analysis.concentration.max_sector.sector}</span><strong>{pct(analysis.concentration.max_sector.weight, 1)}</strong></div>
   <div><span>{p("marketBeta")}</span><strong>{exposure ? beta(exposure.market) : "N/A"}</strong></div>
  </div>
  <div className="detail-grid">
   <section className="panel"><div className="panel-header"><h2>{p("weightVsRisk")}</h2></div>
    <div className={styles.legend}><span><i className={`${styles.swatch} ${styles.weightFill}`}/>{p("legendWeight")}</span><span><i className={`${styles.swatch} ${styles.riskFill}`}/>{p("legendRisk")}</span><span>{p("gap")}</span></div>
    <div className={styles.barRows}>{analysis.allocation.map(a => {
     const share = risk.get(a.ticker) ?? 0, gap = share - a.weight;
     return <div key={a.ticker} className={styles.barRow} title={`${a.ticker} · ${a.name}`}>
      <span>{a.ticker}</span>
      <div className={styles.tracks}><div className={styles.track}><span className={styles.weightFill} style={{ width: `${(a.weight / scale) * 100}%` }}/></div><div className={styles.track}><span className={styles.riskFill} style={{ width: `${(Math.max(share, 0) / scale) * 100}%` }}/></div></div>
      <span className={styles.barValue}>{pct(a.weight)} → {pct(share)}<b className={gap > 1 ? styles.up : gap < -1 ? styles.down : ""}>{pp(gap)}</b></span>
     </div>;
    })}</div>
    <p className="panel-note">{p("weightVsRiskNote")}</p>
   </section>
   <section className="panel"><div className="panel-header"><h2>{p("sectorTitle")}</h2></div>
    <div className={styles.barRows}>{analysis.sector.map(s => <div key={s.sector} className={styles.sectorRow}><span>{s.sector}</span><div className={styles.track}><span className={styles.weightFill} style={{ width: `${s.weight}%` }}/></div><b>{pct(s.weight)}</b></div>)}</div>
    <p className="panel-note">{sectorNote[0]}. {sectorNote.slice(1).join(" ")}</p>
   </section>
   <section className="panel"><div className="panel-header"><h2>{p("corrTitle")}</h2><span className="tag">{analysis.window.days} {p("tradingDays")}</span></div>
    <div className="heatmap-wrap"><table className="heatmap"><thead><tr><th/>{tickers.map(t => <th key={t} scope="col">{t}</th>)}</tr></thead><tbody>
     {tickers.map((row, i) => <tr key={row}><th scope="row">{row}</th>{matrix[i].map((c, j) => <td key={tickers[j]} className={styles.heatCell} title={`${row} · ${tickers[j]}: ${c.toFixed(2)}`} style={i === j ? { background: "#f3f6fa", color: "#8195af" } : { background: corrColor(c), color: Math.abs(c) > 0.55 ? "white" : "#183554" }}>{c.toFixed(2)}</td>)}</tr>)}
    </tbody></table></div>
    <p className="panel-note">{p("corrNote")}</p>
   </section>
   <section className="panel"><div className="panel-header"><h2>{p("factorTitle")}</h2></div>
    {exposure ? <div className="table-scroll"><table><thead><tr><th>{p("asset")}</th><th>{p("factorMarket")}</th><th>{p("factorRate")}</th><th>{p("factorVol")}</th></tr></thead><tbody>
     {exposure.by_asset.map(a => <tr key={a.ticker}><th scope="row">{a.ticker}</th><FactorCells row={a}/></tr>)}
     <tr><th scope="row"><b>{p("portfolioRow")}</b></th><FactorCells row={exposure} bold/></tr>
    </tbody></table></div> : <p>N/A</p>}
    <p className="panel-note">{p("factorNote")} {p("fadedNote")}</p>
   </section>
  </div>
 </>;
}

function shockText(id: string, shock: number, f: ReturnType<typeof useFormat>) {
 if (id === "equity_selloff") return `SPY ${f.signedPct(shock * 100, 1)}`;
 if (id === "rate_shock") return `10Y ${shock > 0 ? "+" : ""}${shock.toFixed(0)}bp`;
 return `VIX ${shock > 0 ? "+" : ""}${shock.toFixed(1)}pt`;
}

export function StressTest({ analysis, scenarios }: { analysis: Analysis; scenarios: Scenarios | null }) {
 const p = usePortfolioCopy();
 const f = useFormat();
 const english = useDashboard().language === "en";
 const limitations = english ? apiTextEn.methodLimitations(analysis.methodology.shock_horizon_days) : analysis.methodology.limitations;
 const note = english ? apiTextEn.scenarioNote : scenarios?.note;
 if (!analysis.stress?.length) return <section className="panel" role="status"><h2>{p("stressTitle")}</h2><p>{p("stressUnavailable")}</p></section>;
 return <>
  <div className={styles.sectionTitle}><span className={styles.step}>STEP 4</span><h2>{p("stressTitle")}</h2><p>{p("stressIntro")}</p></div>
  <div className={styles.stressGrid}>{analysis.stress.map(s => {
   const ref = scenarios?.scenarios.find(item => item.id === s.scenario)?.reference;
   const scale = Math.max(...s.by_asset.map(a => Math.abs(a.loss_usd)), 1);
   const isLoss = s.loss_pct >= 0;
   // When the portfolio beta for this factor is not significant, the sign of the result is not a finding.
   const uncertain = s.significant === false;
   const assetSignificant = new Map(analysis.factor_exposure?.by_asset.map(a => [a.ticker, a.significant?.[s.factor]]) ?? []);
   return <section key={s.scenario} className={`panel ${styles.stressCard}`}>
    <div><h3>{p(s.scenario as PortfolioCopyKey)}</h3><span className={styles.shock}>{shockText(s.scenario, s.shock, f)} · {p("tenDays")}</span>{ref && <div className={styles.reference}>{p("reference")} {ref.start} ~ {ref.end}</div>}</div>
    <div className={styles.headline}><span>{isLoss ? p("loss") : p("gain")}</span><strong className={uncertain ? styles.neutralText : isLoss ? styles.lossText : styles.gainText}>{f.pct(Math.abs(s.loss_pct), 1)}</strong><small>{f.usd(Math.abs(s.loss_usd))}</small>{uncertain && <em className={styles.uncertain}>{p("notSignificant")}</em>}</div>
    <div><h3 className="sr-only">{p("byAsset")}</h3><div className={styles.legend}>{p("byAsset")}</div>
     <div className={styles.barRows}>{s.by_asset.map(a => <div key={a.ticker} className={styles.assetRow}><span>{a.ticker}</span><div className={styles.track}><span className={`${a.loss_usd >= 0 ? styles.lossFill : styles.gainFill} ${assetSignificant.get(a.ticker) === false ? styles.faded : ""}`} style={{ width: `${(Math.abs(a.loss_usd) / scale) * 100}%` }}/></div><b className={assetSignificant.get(a.ticker) === false ? styles.faded : ""}>{f.signedUsd(a.loss_usd)}</b></div>)}</div>
    </div>
   </section>;
  })}</div>
  <section className={`panel ${styles.section}`}><h2>{p("limitations")}</h2><ul className={styles.limitations}>{limitations.map(item => <li key={item}>{item}</li>)}{note && <li>{note}</li>}</ul></section>
 </>;
}

function rowLabel(metric: string, p: (key: PortfolioCopyKey) => string) {
 if (metric === "volatility") return p("volatility_row");
 const loss = metric.match(/^(.*)_loss_(pct|usd)$/);
 if (loss) return `${p(loss[1] as PortfolioCopyKey)} ${p(loss[2] === "pct" ? "lossPct" : "lossUsd")}`;
 return p(metric as PortfolioCopyKey);
}

export function WhatIfTable({ comparison }: { comparison: Comparison }) {
 const p = usePortfolioCopy();
 const f = useFormat();
 const show = (unit: string, v: number) => (unit === "usd" ? f.usd(v) : unit === "beta" ? f.beta(v) : f.pct(v, 2));
 const showChange = (unit: string, v: number) => (unit === "usd" ? f.signedUsd(v) : unit === "beta" ? f.signedBeta(v) : f.pp(v, 2));
 // Stress rows whose portfolio beta is not significant on a side are marked and their change is not colored.
 const uncertain = (side: Analysis, metric: string) => {
  const scenario = metric.match(/^(.*)_loss_(pct|usd)$/)?.[1];
  return scenario !== undefined && side.stress?.find(s => s.scenario === scenario)?.significant === false;
 };
 const detail = (text: string | null, flagged: boolean) => <>{text && <span className={styles.detail}>{text}</span>}{flagged && <span className={styles.detail}>{p("uncertain")}</span>}</>;
 return <>
  <div className="table-scroll"><table><thead><tr><th>{p("metric")}</th><th>{p("current")}</th><th>{p("proposed")}</th><th>{p("change")}</th></tr></thead><tbody>
   {comparison.comparison.map(r => {
    const before = uncertain(comparison.current, r.metric), after = uncertain(comparison.proposed, r.metric);
    return <tr key={r.metric}>
     <th scope="row">{rowLabel(r.metric, p)}</th>
     <td className={before ? styles.faded : ""}>{show(r.unit, r.current)}{detail(r.current_detail, before)}</td>
     <td className={after ? styles.faded : ""}>{show(r.unit, r.proposed)}{detail(r.proposed_detail, after)}</td>
     <td className={before || after ? styles.faded : r.change > 0 ? styles.worse : r.change < 0 ? styles.better : ""}>{showChange(r.unit, r.change)}</td>
    </tr>;
   })}
  </tbody></table></div>
  <p className="panel-note">{p("compareNote")} {p("fadedShort")}</p>
 </>;
}
