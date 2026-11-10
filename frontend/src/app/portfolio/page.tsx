import type { Metadata } from "next";
import PortfolioView from "@/components/portfolio/portfolio-view";

export const metadata: Metadata = {
 title: "M/PRI | Portfolio Risk",
 description: "포트폴리오 집중위험, 팩터 민감도, Stress Test, What-if 비교. Estimates under fixed shock assumptions, not forecasts.",
};

export default function PortfolioPage() { return <PortfolioView/>; }
