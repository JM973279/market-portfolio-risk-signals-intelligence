"use client";
import { useDashboard } from "./dashboard-shell";
import type { PreopenRange } from "@/lib/dashboard-types";

const REPORT_URL = "https://github.com/JM973279/market-portfolio-risk-signals-intelligence/blob/main/reports/signal_checks.md";
const ranges: Record<PreopenRange, [string, string]> = {
 "le_-3": ["−3% or lower", "−3% 이하"],
 "-3_-1": ["−3% to −1%", "−3% 초과 ~ −1%"],
 "-1_1": ["−1% to +1%", "−1% 초과 ~ +1%"],
 "1_3": ["+1% to +3%", "+1% 초과 ~ +3%"],
 "gt_3": ["above +3%", "+3% 초과"],
};
const tickerName = (t: string) => t === "^SOX" ? "SOX" : t;

// Pre-open reference: last US session before the KRX open. Display only, never part of the score.
export default function PreopenUs() {
 const { preopen, language } = useDashboard();
 const ko = language === "ko";
 const pct = (x: number | null | undefined, digits = 2) => typeof x === "number" ? `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(digits)}%` : "N/A";
 const share = (x: number | null | undefined) => typeof x === "number" ? `${(x * 100).toFixed(1)}%` : "N/A";
 const tone = (x: number | null | undefined) => typeof x === "number" && x <= -0.03 ? "negative" : undefined;
 const header = <div className="panel-header"><h2>{ko ? "개장 전 참고 · 전날 밤 미국 시장" : "Pre-open reference · Overnight US session"}</h2><span className="tag">{ko ? "점수 미반영 · 참고용" : "Not in score · Reference only"}</span></div>;
 if (!preopen) return <section className="panel preopen-us">{header}<p>{ko ? "개장 전 미국 가격 자료를 불러오지 못했습니다." : "The pre-open US export is unavailable."}</p></section>;
 const { latest, context, source } = preopen;
 const bucket = context.buckets.find(b => b.key === latest.ewyRange);
 const years = `${context.period.first.slice(0, 4)}~${context.period.last.slice(0, 4)}`;
 const drop = pct(context.drop_threshold, 0);
 return <section className="panel preopen-us" aria-label={ko ? "개장 전 미국 시장 참고" : "Pre-open US market reference"}>
  {header}
  <p>{ko ? "한국 장이 열리기 전에 끝난 미국 세션의 한국 ETF(EWY)와 미국 반도체 지수(SOX) 하루 수익률입니다. 사전 등록 실험에서 다음 거래일 −2% 이하 하락을 가려내는 데 도움이 된 신호지만, Risk Score·MSI에는 넣지 않습니다." : "One-session returns of the US-listed Korea ETF (EWY) and the US semiconductor index (SOX) from the US session that closed before the KRX open. A pre-registered check found they help flag −2% sessions, but they are not part of the Risk Score or MSI."}</p>
  <div className="selected-metrics">
   <div><span>{ko ? "적용 한국 거래일" : "KRX session"}</span><strong className="selected-date">{latest.krxDate}</strong></div>
   <div><span>{ko ? "기준 미국 세션" : "US session"}</span><strong className="selected-date">{latest.usDate}</strong></div>
   {preopen.tickers.map(t => <div key={t}><span>{tickerName(t)}</span><strong className={tone(latest.returns[t])}>{pct(latest.returns[t])}</strong></div>)}
  </div>
  {bucket && <p role="status">{ko
   ? `${years}년에 EWY가 ${ranges[bucket.key][1]}였던 다음 한국 거래일 ${bucket.sessions.toLocaleString("ko-KR")}일 중 KOSPI200이 ${drop} 이하로 내린 날은 ${share(bucket.drop_share)}였습니다 (전체 평균 ${share(context.all.drop_share)}).`
   : `In ${years}, after EWY moved ${ranges[bucket.key][0]}, KOSPI200 fell ${drop} or more on ${share(bucket.drop_share)} of the next ${bucket.sessions.toLocaleString("en-US")} KRX sessions (all sessions: ${share(context.all.drop_share)}).`}</p>}
  <div className="table-scroll"><table><caption>{ko ? `EWY 구간별 다음 한국 거래일 KOSPI200 (${years}년 설계 구간, 2026년 제외)` : `KOSPI200 on the next KRX session by EWY range (${years} design period, 2026 excluded)`}</caption><thead><tr><th>{ko ? "전날 밤 EWY" : "Overnight EWY"}</th><th>{ko ? "거래일 수" : "Sessions"}</th><th>{ko ? `${drop} 이하 하락 비율` : `Share at ${drop} or worse`}</th><th>{ko ? "KOSPI200 중앙값" : "Median KOSPI200"}</th></tr></thead><tbody>
   {context.buckets.map(b => <tr key={b.key} className={b.key === latest.ewyRange ? "preopen-current" : undefined}><th scope="row">{ranges[b.key][ko ? 1 : 0]}{b.key === latest.ewyRange && <small> · {ko ? "현재" : "now"}</small>}</th><td>{b.sessions.toLocaleString("en-US")}</td><td>{share(b.drop_share)}</td><td>{pct(b.median_return)}</td></tr>)}
   <tr><th scope="row">{ko ? "전체" : "All"}</th><td>{context.all.sessions.toLocaleString("en-US")}</td><td>{share(context.all.drop_share)}</td><td>{pct(context.all.median_return)}</td></tr>
  </tbody></table></div>
  <p className="panel-note">{ko ? "과거 빈도이며 예측 확률이 아닙니다. 큰 상승 뒤에도 하락 비율이 높은 것처럼, 미국 쪽 큰 움직임은 방향보다 변동성이 커졌다는 신호에 가깝습니다. EWY 수익률에는 원/달러 환율과 한국 전 거래일 장중 움직임도 일부 섞여 있습니다. −3% 이하 큰 하락에서는 개선이 확인되지 않았습니다." : "Historical frequencies, not forecast probabilities. Large US moves in either direction mostly signal higher volatility. EWY returns also carry KRW/USD moves and part of the previous KRX session. No improvement was found for −3% sessions."}</p>
  <details><summary>{ko ? `최근 ${preopen.history.length}개 한국 거래일` : `Last ${preopen.history.length} KRX sessions`}</summary><div className="table-scroll"><table><thead><tr><th>{ko ? "한국 거래일" : "KRX session"}</th><th>{ko ? "미국 세션" : "US session"}</th>{preopen.tickers.map(t => <th key={t}>{tickerName(t)}</th>)}</tr></thead><tbody>{preopen.history.map(p => <tr key={p.krxDate}><th scope="row">{p.krxDate}</th><td>{p.usDate}</td>{preopen.tickers.map(t => <td key={t} className={tone(p.returns[t])}>{pct(p.returns[t])}</td>)}</tr>)}</tbody></table></div></details>
  <p className="panel-note">{ko ? "자료" : "Data"}: {source.provider ?? "Yahoo Finance"} · {ko ? "마지막 미국 세션" : "last US session"} {source.lastUsSession} · {ko ? "수집 시각 (UTC)" : "retrieved (UTC)"} {source.retrievedAt ?? "N/A"} · {ko ? `GitHub Actions가 4시간마다 수집·검증하며, 다음 미국 세션(${source.nextUsSession})이 마감되면 갱신됩니다.` : `Collected and verified by GitHub Actions every 4 hours; updates after the next US session (${source.nextUsSession}) closes.`} <a href={REPORT_URL}>{ko ? "사전 등록 실험 결과" : "Pre-registered check"} →</a> · <a href="/data/korea-preopen.json" download>JSON</a></p>
 </section>;
}
