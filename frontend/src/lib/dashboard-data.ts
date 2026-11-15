import "server-only";
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { DashboardData, GlobalData, MonitorData, OperationalData, PreopenData, ScenarioLibraryData } from "./dashboard-types";
export async function getDashboardData(): Promise<DashboardData> {
 "use cache";
 let monitor: MonitorData | null = null;
 let global: GlobalData | null = null;
 try {
  const parsed = JSON.parse(await readFile(path.join(process.cwd(), "public/data/korea-monitor.json"), "utf8"));
  if (parsed.schema_version === 1 && Array.isArray(parsed.history) && parsed.sources && parsed.evidence) monitor = parsed;
 } catch { /* Availability is shown in the UI. */ }
 try {
  const parsed = JSON.parse(await readFile(path.join(process.cwd(), "public/data/global-markets.json"), "utf8"));
  if (parsed.schema_version === 1 && Array.isArray(parsed.us) && Array.isArray(parsed.korea) && parsed.sources) global = parsed;
 } catch { /* Optional original-V1 evidence never blocks Korea research. */ }
 let operational: OperationalData | null = null;
 try {
  const parsed = JSON.parse(await readFile(path.join(process.cwd(), "public/data/operational-markets.json"), "utf8"));
  if (parsed.schema_version === 1 && parsed.markets?.us && parsed.markets?.korea && typeof parsed.generatedAt === "string") operational = parsed;
 } catch { /* Operational availability does not block historical research or Portfolio. */ }
 let scenarios: ScenarioLibraryData | null = null;
 try {
  const parsed = JSON.parse(await readFile(path.join(process.cwd(), "public/data/korea-scenarios.json"), "utf8"));
  if (parsed.schema_version === 1 && parsed.is_forecast === false && Array.isArray(parsed.episodes) && Array.isArray(parsed.summary) && parsed.categories) scenarios = parsed;
 } catch { /* The scenario library is optional; Case Studies still renders the holdout. */ }
 let usScenarios: ScenarioLibraryData | null = null;
 try {
  const parsed = JSON.parse(await readFile(path.join(process.cwd(), "public/data/us-scenarios.json"), "utf8"));
  if (parsed.schema_version === 1 && parsed.is_forecast === false && Array.isArray(parsed.episodes) && Array.isArray(parsed.summary) && parsed.categories) usScenarios = parsed;
 } catch { /* The US library is optional; the Korea library still renders. */ }
 let preopen: PreopenData | null = null;
 try {
  const parsed = JSON.parse(await readFile(path.join(process.cwd(), "public/data/korea-preopen.json"), "utf8"));
  if (parsed.schema_version === 1 && parsed.is_forecast === false && parsed.latest?.krxDate && Array.isArray(parsed.history) && Array.isArray(parsed.context?.buckets)) preopen = parsed;
 } catch { /* Pre-open reference is display only; the Korea page renders without it. */ }
 return { monitor, global, operational, scenarios, usScenarios, preopen };
}
