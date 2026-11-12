import type { MarketPoint } from "./dashboard-types";
export const chartRanges = ["1M", "3M", "6M", "1Y", "ALL"] as const;
export type ChartRange = typeof chartRanges[number];
export const timestamp = (day: string) => Date.parse(`${day}T00:00:00Z`);
export function rangeStart(end: string, range: ChartRange, first: string) {
 if (range === "ALL") return timestamp(first);
 const date = new Date(timestamp(end));
 const months = range === "1Y" ? 12 : Number(range.replace("M", ""));
 const day = date.getUTCDate();
 date.setUTCDate(1);
 date.setUTCMonth(date.getUTCMonth() - months);
 const last = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth()+1, 0)).getUTCDate();
 date.setUTCDate(Math.min(day,last));
 return date.getTime();
}
export function linePath(points: MarketPoint[], key: "price" | "risk", x: (day: string) => number, y: (value: number) => number) {
 let previous = false;
 return points.map(point => {
  const value = point[key];
  if (value === null || !Number.isFinite(value)) { previous = false; return ""; }
  const command = previous ? "L" : "M";
  previous = true;
  return `${command}${x(point.date).toFixed(2)},${y(value).toFixed(2)}`;
 }).join(" ");
}

// 차트 시계열 = 고정 연구 export(과거 OOS·가격) + 운영 export(고정 모델 추론 V1·MSI·임계값).
// - 같은 날짜에 연구 값이 있으면 그대로 둔다. 연구 값이 비어 있는 칸만 운영 추론 값으로 채운다
//   (서로 다른 실제 기록을 합치는 것이며, 앞 날짜 값을 이월하지 않는다).
// - 운영 export에는 가격이 없으므로(sourceValuesIncluded=false) 그 구간 가격선은 비워 둔다.
export function mergeOperational(points: MarketPoint[], history: MarketPoint[] | undefined): MarketPoint[] {
 if (!history?.length) return points;
 const byDate = new Map(points.map(point => [point.date, {...point}]));
 for (const op of history) {
  const base = byDate.get(op.date);
  if (!base) { byDate.set(op.date, {date: op.date, price: null, risk: op.risk, msi: op.msi, threshold: op.threshold}); continue; }
  if (base.risk === null) base.risk = op.risk;
  if (base.msi === null) base.msi = op.msi;
  if (base.threshold === null) base.threshold = op.threshold;
 }
 return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date));
}
