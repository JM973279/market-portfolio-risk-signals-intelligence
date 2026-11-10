import type { MonitorData } from "@/components/korea-monitor";
export type { MonitorData };
export type MarketPoint = { date: string; price: number | null; risk: number | null; msi: number | null; threshold: number | null; stress?: number | null };
export type Source = { project: string; path: string; rows: number; first?: string | null; latest: string | null; sha256?: string };
export type GlobalData = { schema_version: number; asOf: string | null; us: MarketPoint[]; korea: MarketPoint[]; usMetrics: { horizon: string; auc: number; precision: number; recall: number; f1: number; start: string; end: string; n: number }[]; correlation: { date: string; values: (number | null)[] }[]; sources: Record<string, Source>; issues: string[] };
export type OperationalPoint = MarketPoint & { recordType: "OPERATIONAL" | "RETROSPECTIVE_INFERENCE" };
export type OperationalMarketData = {
 status: "CURRENT" | "DELAYED" | "UNAVAILABLE" | "BLOCKED"; expectedDate: string | null;
 current: OperationalPoint | null; lastValid: OperationalPoint | null; history: OperationalPoint[];
 reason: string | null; modelSha256: string; trainingEvidence: string;
 series: { name: string; provider: string; observationDate: string | null; retrievedAt: string | null; status: string; reason: string | null }[];
 inferenceAt?: string; availabilityOrigin?: string;
 availability?: { date: string; available: string[]; missing: string[]; values?: Record<string, number | null> }[];
};
export type OperationalData = { schema_version: 1; generatedAt: string; markets: { us: OperationalMarketData; korea: OperationalMarketData } };
export type DashboardData = { monitor: MonitorData | null; global: GlobalData | null; operational?: OperationalData | null };
export const views = ["us", "korea", "breadth", "validation", "cases", "sources", "methodology"] as const;
export type View = "dashboard" | typeof views[number];
