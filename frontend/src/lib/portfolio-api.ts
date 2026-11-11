// Portfolio API (FastAPI, src/portfolio/server.py) types and calls.
// Same-origin proxy by default; an explicit public URL is an optional build-time override.
export const PORTFOLIO_API = process.env.NEXT_PUBLIC_PORTFOLIO_API_URL ?? "";

export type Factor = "market" | "rate" | "volatility";
export type Holding = { ticker: string; weight: number };
export type Asset = { ticker: string; name: string; type: string; sector: string; asset_class: string };
export type SectorMethodology = { classification: string; etf_lookthrough: boolean; label: string; limitations: string[] };
export type Methodology = { regression: string; beta_frequency: string; significance_t?: number; shock_horizon_days: number; approximation: string; scenarios_additive: boolean; is_forecast: boolean; limitations: string[] };
export type Universe = { assets: Asset[]; sector_methodology: SectorMethodology };
export type Scenario = { id: string; name: string; definition: string; factor: Factor; unit: "return" | "bp" | "pt"; rule: string; pnl_method: string; shock: number; reference: { start: string; end: string } };
export type Scenarios = { as_of: string; lookback_start: string; horizon_days: number; note: string; methodology: Methodology; scenarios: Scenario[] };
export type FactorBeta = { market: number; rate: number; volatility: number };
// t value per factor (null = perfect fit) and whether |t| >= methodology.significance_t.
export type FactorSignificance = { t_stat?: Record<Factor, number | null> | null; significant?: Record<Factor, boolean> | null };
export type StressResult = { scenario: string; name: string; factor: Factor; shock: number; unit: string; loss_pct: number; loss_usd: number; by_asset: { ticker: string; loss_usd: number }[]; significant?: boolean | null };
export type Analysis = {
 as_of: string; window: { start: string; end: string; days: number }; value_usd: number;
 allocation: { ticker: string; name: string; sector: string; weight: number }[];
 sector: { sector: string; weight: number }[]; sector_methodology: SectorMethodology;
 concentration: { max_asset: { ticker: string; weight: number }; max_sector: { sector: string; weight: number } };
 correlation: { tickers: string[]; matrix: number[][] }; volatility: number;
 risk_contribution: { ticker: string; share: number }[]; methodology: Methodology;
 factor_exposure: (FactorBeta & FactorSignificance & { by_asset: (FactorBeta & FactorSignificance & { ticker: string })[] }) | null;
 stress: StressResult[] | null;
};
export type ComparisonRow = { metric: string; label: string; unit: "%" | "usd" | "beta"; current: number; proposed: number; change: number; current_detail: string | null; proposed_detail: string | null };
export type Comparison = { current: Analysis; proposed: Analysis; comparison: ComparisonRow[] };

// "network": the server could not be reached. "rejected": the API answered with an error (e.g. 422).
export class PortfolioApiError extends Error {
 kind: "network" | "rejected" | "unavailable";
 constructor(kind: "network" | "rejected" | "unavailable", message: string) { super(message); this.kind = kind; }
}

async function request<T>(path: string, body?: unknown): Promise<T> {
 let response: Response;
 try {
  response = await fetch(`${PORTFOLIO_API}/api/portfolio${path}`, body === undefined ? { signal: AbortSignal.timeout(30_000) } : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(30_000) });
 } catch {
  throw new PortfolioApiError("network", PORTFOLIO_API);
 }
 if (!response.ok) {
  const payload = await response.json().catch(() => null);
  const messages = Array.isArray(payload?.detail) ? payload.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")) : [response.statusText];
  throw new PortfolioApiError(response.status >= 500 ? "unavailable" : "rejected", messages.join(" · "));
 }
 try { return await response.json() as T; }
 catch { throw new PortfolioApiError("unavailable", "Invalid JSON response"); }
}

export const getUniverse = () => request<Universe>("/universe");
export const getScenarios = () => request<Scenarios>("/scenarios");
export const analyzePortfolio = (holdings: Holding[], value_usd: number) => request<Analysis>("/analyze", { holdings, value_usd });
export const comparePortfolios = (current: Holding[], proposed: Holding[], value_usd: number) =>
 request<Comparison>("/compare", { current: { holdings: current, value_usd }, proposed: { holdings: proposed, value_usd } });

// Same rules as the API (schemas.py) so the form can explain problems before sending.
export const MAX_HOLDINGS = 10;
export type InputProblem = "empty" | "duplicate" | "max" | "sum" | "value" | null;
export function inputProblem(holdings: Holding[], value: number): InputProblem {
 if (holdings.length === 0 || holdings.some(h => !h.ticker.trim() || !Number.isFinite(h.weight) || !(h.weight > 0) || h.weight > 100)) return "empty";
 if (holdings.length > MAX_HOLDINGS) return "max";
 if (new Set(holdings.map(h => h.ticker.trim().toUpperCase())).size !== holdings.length) return "duplicate";
 if (Math.abs(weightTotal(holdings) - 100) > 0.01) return "sum";
 if (!(value > 0) || !Number.isFinite(value)) return "value";
 return null;
}
export const weightTotal = (holdings: Holding[]) => holdings.reduce((sum, h) => sum + (Number.isFinite(h.weight) ? h.weight : 0), 0);

// Demo portfolios (same as examples/portfolio on the portfolio branch).
export const exampleBefore: Holding[] = [{ ticker: "AAPL", weight: 30 }, { ticker: "MSFT", weight: 30 }, { ticker: "NVDA", weight: 20 }, { ticker: "AMZN", weight: 20 }];
export const exampleAfter: Holding[] = [{ ticker: "AAPL", weight: 21 }, { ticker: "MSFT", weight: 21 }, { ticker: "NVDA", weight: 14 }, { ticker: "AMZN", weight: 14 }, { ticker: "TLT", weight: 30 }];
