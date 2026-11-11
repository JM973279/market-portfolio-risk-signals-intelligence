import type { Metadata } from "next";
import MqsPortfolioFrame from "@/components/mqs-portfolio-frame";

export const metadata: Metadata = {
 title: "M/PRI | Portfolio Analysis",
 description: "mqs 포트폴리오 성과·벤치마크 요인분해, 위험, 역사적 재현. Hypothetical past performance, not forecasts.",
};

// 배포 저장소의 Portfolio API 화면 대신 이 저장소(mqs)의 포트폴리오 분석을 보여 준다.
export default function PortfolioPage() { return <MqsPortfolioFrame/>; }
