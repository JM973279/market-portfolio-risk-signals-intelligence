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
export type ScenarioVerdict = "warned" | "borderline" | "missed" | "no_data";
export type ScenarioNote = "price_missing" | "window_incomplete" | "trough_at_window_end" | "source_unverified" | "window_overlaps";
export type ScenarioEpisode = {
 id: string; onset: string; tier: "core" | "supporting"; category: string; geo: "foreign" | "domestic" | "both";
 name: { en: string; ko: string }; cause: { en: string; ko: string }; category_note?: { en: string; ko: string };
 source: { title: string; url: string } | null;
 metrics: { reference_date: string; onset_return: number; max_drawdown: number; trough_date: string; sessions_to_trough: number; recovery_date: string | null; sessions_to_recover: number | null; window_sessions: number; window_end_date: string; window_complete: boolean; trough_at_window_end: boolean; price_last_date: string } | null;
 model: { verdict: ScenarioVerdict; prior_risk: number | null; prior_date: string | null; prior_warning_sessions: number | null; prior_observed_sessions: number; msi: number | null; threshold: number | null; msi_recognized: boolean | null; origin: string | null };
 notes: ScenarioNote[]; overlaps: string[];
};
export type ScenarioSummary = { category: string; episodes: number; with_prices: number; median_max_drawdown: number | null; worst_max_drawdown: number | null; warned: number; judged: number };
export type ScenarioLibraryData = {
 schema_version: 1; asOf: string; is_forecast: false;
 parameters: { window_sessions: number; prior_sessions: number };
 taxonomy: { name: string; url: string; note: string };
 sources?: Record<string, { path: string; sha256: string }>;
 categories: Record<string, string>; summary: ScenarioSummary[]; episodes: ScenarioEpisode[];
};
export type PreopenRange = "le_-3" | "-3_-1" | "-1_1" | "1_3" | "gt_3";
export type PreopenPoint = { krxDate: string; usDate: string; returns: Record<string, number | null>; ewyRange: PreopenRange | null };
export type PreopenStats = { sessions: number; drop_share: number | null; median_return: number | null };
export type PreopenData = {
 schema_version: 1; is_forecast: false; use: string; tickers: string[];
 source: { path: string; sha256: string; provider: string | null; retrievedAt: string | null; lastUsSession: string; nextUsSession: string };
 latest: PreopenPoint; history: PreopenPoint[];
 context: { period: { first: string; last: string }; drop_threshold: number; all: PreopenStats; buckets: (PreopenStats & { key: PreopenRange; low: number | null; high: number | null })[] };
 report: string;
};
export type DashboardData = { monitor: MonitorData | null; global: GlobalData | null; operational?: OperationalData | null; scenarios?: ScenarioLibraryData | null; usScenarios?: ScenarioLibraryData | null; preopen?: PreopenData | null };
export const views = ["us", "korea", "breadth", "validation", "cases", "sources", "methodology"] as const;
export type View = "dashboard" | typeof views[number];
