"use client";
// mqs 포트폴리오 분석(qsignals.portfolio_server)을 사이트 안에 보여 준다.
// - /portfolio-lab, /portfolio/{app.js,style.css}, /api/portfolio/* 는 next.config.ts 가
//   mqs 포트폴리오 서버로 넘긴다(같은 출처라 iframe 높이를 내용에 맞출 수 있다).
// - EN 토글이면 ?lang=en 을 붙여 iframe 안 화면과 API 응답도 영어로 바꾼다(주소가 바뀌면 다시 불러온다).
// - 서버가 꺼져 있으면 iframe 안에 오류가 보이므로, 아래 안내 문구로 실행 방법을 함께 적는다.
import { useEffect, useRef, useState } from "react";
import { useDashboard } from "./dashboard-shell";

export default function MqsPortfolioFrame() {
 const { language } = useDashboard();
 const ko = language !== "en";
 const frame = useRef<HTMLIFrameElement>(null);
 const [height, setHeight] = useState(1600);
 useEffect(() => {
  const node = frame.current;
  if (!node) return;
  let observer: ResizeObserver | null = null;
  const fit = () => {
   const body = node.contentDocument?.body;
   if (!body) return;
   const update = () => setHeight(Math.max(800, body.scrollHeight + 24));
   update();
   observer?.disconnect();
   observer = new ResizeObserver(update);
   observer.observe(body);
  };
  node.addEventListener("load", fit);
  fit();
  return () => { node.removeEventListener("load", fit); observer?.disconnect(); };
 }, []);
 return <main className="dashboard-content view-portfolio">
  <div className="page-hero compact-hero"><div className="hero-copy"><p className="eyebrow">{ko ? "포트폴리오 분석 · Market Qualitative Signals" : "Portfolio analysis · Market Qualitative Signals"}</p><h1>{ko ? "포트폴리오 분석" : "Portfolio Analysis"}</h1><p className="hero-subtitle">{ko ? "과거 가상성과, 수익 기여도, 벤치마크 대비 성과요인, 위험과 역사적 재현을 한 화면에서 봅니다." : "Hypothetical past performance, contribution, benchmark attribution, risk and historical replay."}</p></div></div>
  <iframe ref={frame} className="mqs-portfolio-frame" src={ko ? "/portfolio-lab" : "/portfolio-lab?lang=en"} title={ko ? "포트폴리오 분석" : "Portfolio analysis"} style={{ height }}/>
  <p className="panel-note">{ko ? "검증된 GitHub 포트폴리오 자료만 읽는 mqs 포트폴리오 서버(python3 -m qsignals.portfolio_server)가 켜져 있어야 합니다." : "Requires the mqs portfolio server (python3 -m qsignals.portfolio_server), which reads only verified GitHub portfolio data."}</p>
 </main>;
}
