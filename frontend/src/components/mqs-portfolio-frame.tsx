"use client";
// mqs 포트폴리오 분석(qsignals.portfolio_server)을 사이트 안에 보여 준다. 한 메뉴 안에 시장별 탭 두 개:
// - 한국: /portfolio-kr-lab, /api/portfolio-kr/* → 같은 서버의 한국 전용 데이터 경로
// - 미국: /portfolio-lab, /api/portfolio/* → 미국 포트폴리오 서버
//   (next.config.ts 가 넘긴다. 같은 출처라 iframe 높이를 내용에 맞출 수 있다.)
// 탭 순서와 처음 열리는 탭은 화면 언어를 따른다(KR: 한국 → 미국, EN: US → Korea).
// 주소 끝의 #korea / #us 로 보던 탭을 유지한다.
import { useEffect, useRef, useState } from "react";
import { useDashboard } from "./dashboard-shell";
import { marketOrder, type Market } from "@/lib/market-order";

const fromHash = (): Market | null => {
 const hash = typeof window === "undefined" ? "" : window.location.hash.slice(1);
 return hash === "korea" || hash === "us" ? hash : null;
};

export default function MqsPortfolioFrame() {
 const { language } = useDashboard();
 const ko = language !== "en";
 const order = marketOrder(language);
 const [chosen, setChosen] = useState<Market | null>(null);
 const market: Market = chosen ?? order[0];
 const korea = market === "korea";
 const frame = useRef<HTMLIFrameElement>(null);
 const [height, setHeight] = useState(1600);
 useEffect(() => {
  const sync = () => setChosen(fromHash());
  const timer = setTimeout(sync, 0);
  window.addEventListener("hashchange", sync);
  return () => { clearTimeout(timer); window.removeEventListener("hashchange", sync); };
 }, []);
 const observers = useRef<{ disconnect(): void }[]>([]);
 const stop = () => { observers.current.forEach(o => o.disconnect()); observers.current = []; };
 // iframe 문서의 높이에 맞춘다. 로드 이벤트(onLoad)와, 이미 로드된 경우(마운트 직후) 둘 다에서 부른다.
 // 크기 변화(ResizeObserver)와 내용 변화(MutationObserver)를 함께 본다. 화면이 그려지지 않는 동안에는
 // 크기 변화 알림이 늦을 수 있어, 분석 결과가 들어오는 순간(내용 변화)에도 다시 잰다.
 const fit = (node: HTMLIFrameElement | null) => {
  const doc = node?.contentDocument;
  if (!doc?.body || doc.location.href === "about:blank") return;
  const update = () => setHeight(Math.max(800, doc.documentElement.scrollHeight + 24));
  update();
  stop();
  const resize = new ResizeObserver(update);
  resize.observe(doc.body);
  const mutate = new MutationObserver(update);
  mutate.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "open", "class"] });
  observers.current = [resize, mutate];
 };
 useEffect(() => {
  fit(frame.current);
  return stop;
 }, [market]); // 탭을 바꾸면 iframe이 새로 만들어지므로 다시 연결한다.
 const select = (next: Market) => { setChosen(next); history.replaceState(null, "", `#${next}`); };
 const tabLabel = (m: Market) => m === "korea" ? (ko ? "한국 (원화)" : "Korea (KRW)") : (ko ? "미국 (달러)" : "US (USD)");
 const subtitle = korea
  ? (ko ? "국내 상장 주식·ETF의 과거 가상성과, 수익 기여도, KODEX 200 대비 성과요인, 위험과 역사적 재현을 원화 기준으로 봅니다." : "Korean listed stocks and ETFs in KRW: hypothetical past performance, attribution against KODEX 200, risk and historical replay.")
  : (ko ? "미국 상장 주식·ETF의 과거 가상성과, 수익 기여도, 벤치마크 대비 성과요인, 위험과 역사적 재현을 달러 기준으로 봅니다." : "US listed stocks and ETFs in USD: hypothetical past performance, contribution, benchmark attribution, risk and historical replay.");
 const note = korea
  ? (ko ? "한국 포트폴리오는 검증된 국내 주식·ETF 자료가 연결된 경우에 이용할 수 있습니다. 한국 시장 점수·시나리오와 포트폴리오 입력은 별도 자료입니다." : "Korean portfolio analysis requires verified Korean stock and ETF data. Korean market scores and scenarios use separate inputs.")
  : (ko ? "GitHub에 저장된 검증 자료로 계산합니다. 가격과 위험 추정의 실제 관측일은 분석 결과에서 확인하세요." : "Calculations use verified data stored in GitHub. Check the actual price and risk observation dates in the analysis results.");
 const title = ko ? "포트폴리오 분석" : "Portfolio Analysis";
 return <main className="dashboard-content view-portfolio">
  <div className="page-hero compact-hero"><div className="hero-copy"><p className="eyebrow">{`${title} · Market Qualitative Signals`}</p><h1>{title}</h1><p className="hero-subtitle">{subtitle}</p></div></div>
  <div className="page-controls small-toggle portfolio-tabs" role="tablist" aria-label={title}>{order.map(m => <button key={m} type="button" role="tab" id={`portfolio-tab-${m}`} aria-selected={market === m} aria-controls="portfolio-panel" aria-pressed={market === m} onClick={() => select(m)}>{tabLabel(m)}</button>)}</div>
  <div id="portfolio-panel" role="tabpanel" aria-labelledby={`portfolio-tab-${market}`}>
   <iframe ref={frame} key={market} className="mqs-portfolio-frame" src={(korea ? "/portfolio-kr-lab" : "/portfolio-lab") + (ko ? "" : "?lang=en")} onLoad={e => fit(e.currentTarget)} title={`${title} · ${tabLabel(market)}`} style={{ height }}/>
  </div>
  <p className="panel-note">{note}</p>
 </main>;
}
