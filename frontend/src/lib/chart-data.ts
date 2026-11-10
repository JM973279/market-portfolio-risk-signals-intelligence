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
