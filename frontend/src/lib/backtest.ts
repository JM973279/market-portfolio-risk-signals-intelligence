// Backtest of the stored 10-day V1 OOS predictions. Pure functions: no fetching, no model re-run.
// Label: a day is "stress ahead" when MSI is above its threshold on any of the next `horizon`
// sessions (t+1 … t+horizon). With horizon 10 and a 50% cut-off this reproduces the reported
// US 10D precision and recall exactly, so every number here stays consistent with the stored results.
import type { MarketPoint } from "./dashboard-types";

export const HORIZON = 10;
export const EPISODE_GAP = 20;

export type Counts = { tp: number; fp: number; fn: number; tn: number; n: number; precision: number | null; recall: number | null; f1: number | null; warnings: number; positives: number };
export type YearRow = Counts & { year: string };
export type Episode = { onset: string; end: string; stressDays: number; verdict: "warned" | "missed" | "noData"; lead: number | null; priorRisk: number | null; priorDate: string | null; peakMsi: number | null };

// Stress on the day itself: the stored flag when present, otherwise MSI above its threshold.
export function stressFlags(points: MarketPoint[]): (boolean | null)[] {
 return points.map(p => {
  if (p.stress === 0 || p.stress === 1) return p.stress === 1;
  if (p.msi === null || p.threshold === null || !Number.isFinite(p.msi) || !Number.isFinite(p.threshold)) return null;
  return p.msi > p.threshold;
 });
}

// Forward label; null when the window is incomplete or holds a missing observation.
export function forwardLabels(points: MarketPoint[], horizon = HORIZON): (boolean | null)[] {
 const s = stressFlags(points);
 return points.map((_, i) => {
  if (i + horizon >= points.length) return null;
  const window = s.slice(i + 1, i + 1 + horizon);
  return window.some(v => v === null) ? null : window.some(v => v === true);
 });
}

function ratio(a: number, b: number) { return b > 0 ? a / b : null; }

export function counts(points: MarketPoint[], labels: (boolean | null)[], cut: number, from = 0, to = points.length): Counts {
 let tp = 0, fp = 0, fn = 0, tn = 0;
 for (let i = from; i < to; i++) {
  const risk = points[i].risk, y = labels[i];
  if (risk === null || !Number.isFinite(risk) || y === null) continue;
  const warn = risk >= cut;
  if (warn && y) tp++; else if (warn) fp++; else if (y) fn++; else tn++;
 }
 const precision = ratio(tp, tp + fp), recall = ratio(tp, tp + fn);
 const f1 = precision !== null && recall !== null && precision + recall > 0 ? 2 * precision * recall / (precision + recall) : null;
 return { tp, fp, fn, tn, n: tp + fp + fn + tn, precision, recall, f1, warnings: tp + fp, positives: tp + fn };
}

// Rank-based ROC-AUC (ties count half). Independent of the cut-off.
export function rocAuc(points: MarketPoint[], labels: (boolean | null)[]): number | null {
 const rows: [number, boolean][] = [];
 points.forEach((p, i) => { const y = labels[i]; if (p.risk !== null && Number.isFinite(p.risk) && y !== null) rows.push([p.risk, y]); });
 const pos = rows.filter(r => r[1]).length, neg = rows.length - pos;
 if (!pos || !neg) return null;
 rows.sort((a, b) => a[0] - b[0]);
 let rankSum = 0;
 for (let i = 0; i < rows.length;) {
  let j = i;
  while (j + 1 < rows.length && rows[j + 1][0] === rows[i][0]) j++;
  const rank = (i + j + 2) / 2;
  for (let k = i; k <= j; k++) if (rows[k][1]) rankSum += rank;
  i = j + 1;
 }
 return (rankSum - pos * (pos + 1) / 2) / (pos * neg);
}

export function byYear(points: MarketPoint[], labels: (boolean | null)[], cut: number): YearRow[] {
 const years: YearRow[] = [];
 let start = 0;
 for (let i = 1; i <= points.length; i++) {
  if (i === points.length || points[i].date.slice(0, 4) !== points[start].date.slice(0, 4)) {
   const row = counts(points, labels, cut, start, i);
   if (row.n) years.push({ year: points[start].date.slice(0, 4), ...row });
   start = i;
  }
 }
 return years;
}

// Stress days closer than `gap` calm sessions belong to one episode, so a warning that carries
// over from the previous burst is not counted as a fresh advance warning.
// An episode is "warned" when V1 was at or above the cut-off on one of the `horizon` sessions
// before its first stress day; lead = sessions from that first warning to the onset.
export function episodes(points: MarketPoint[], cut: number, gap = EPISODE_GAP, horizon = HORIZON): Episode[] {
 const s = stressFlags(points);
 const spans: [number, number][] = [];
 let calm = Infinity;
 s.forEach((v, i) => {
  if (v === true) {
   if (spans.length && calm < gap) spans[spans.length - 1][1] = i; else spans.push([i, i]);
   calm = 0;
  } else if (v === false) calm++;
 });
 return spans.map(([a, b]) => {
  const prior = points.slice(Math.max(0, a - horizon), a).map((p, k) => ({ p, k: Math.max(0, a - horizon) + k })).filter(({ p }) => p.risk !== null && Number.isFinite(p.risk));
  const first = prior.find(({ p }) => (p.risk as number) >= cut);
  const last = prior.at(-1);
  let stressDays = 0, peak: number | null = null;
  for (let i = a; i <= b; i++) {
   if (s[i]) stressDays++;
   const m = points[i].msi;
   if (s[i] && m !== null && (peak === null || m > peak)) peak = m;
  }
  return {
   onset: points[a].date, end: points[b].date, stressDays,
   verdict: !prior.length ? "noData" : first ? "warned" : "missed",
   lead: first ? a - first.k : null,
   priorRisk: last ? last.p.risk : null, priorDate: last ? last.p.date : null, peakMsi: peak,
  };
 });
}

// The OOS span: first and last day that has both a prediction and a complete label.
export function oosSpan(points: MarketPoint[], labels: (boolean | null)[]) {
 const idx = points.map((p, i) => (p.risk !== null && labels[i] !== null ? i : -1)).filter(i => i >= 0);
 return idx.length ? { first: points[idx[0]].date, last: points[idx[idx.length - 1]].date } : null;
}
