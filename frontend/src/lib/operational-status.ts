import type { DashboardData, OperationalMarketData, OperationalPoint } from "./dashboard-types";
import type { Language } from "./monitor-copy";

// Header date: the operational export's observation date when one exists (per market on a
// market page, the newest of both elsewhere); otherwise the static research snapshot date.
export function headerSnapshot(data: Pick<DashboardData, "global" | "monitor" | "operational">, country?: "us" | "korea"): { operational: boolean; date: string | null } {
 const markets = data.operational?.markets;
 const dates = (country ? [markets?.[country]] : [markets?.us, markets?.korea])
  .map(market => market?.expectedDate)
  .filter((date): date is string => typeof date === "string" && date.length > 0)
  .sort();
 const latest = dates.at(-1);
 if (latest) return { operational: true, date: latest };
 return { operational: false, date: data.global?.asOf ?? data.monitor?.latest?.Date ?? null };
}

// A past record is never a fallback for a missing or blocked current observation.
export function currentOperationalPoint(market?: OperationalMarketData | null): OperationalPoint | null {
 const point = market?.current;
 if (market?.status !== "CURRENT" || !point || point.date !== market.expectedDate) return null;
 if (![point.risk, point.msi, point.threshold].every(value => typeof value === "number" && Number.isFinite(value))) return null;
 if (point.risk! < 0 || point.risk! > 1) return null;
 return point;
}

export function operationalMessage(market: OperationalMarketData | null | undefined, language: Language): string {
 const ko = language === "ko";
 if (!market) return ko ? "운영 export가 없습니다. 수집·검증 후 다시 빌드해야 합니다." : "No operational export. Collect, validate and rebuild.";
 if (currentOperationalPoint(market)) return ko ? "표시한 관측일의 필수 원천과 고정 모델 추론이 검증되었습니다. 실시간 자동 갱신 자료는 아닙니다." : "Required sources and frozen model inference are verified for the displayed observation date. This is a manually refreshed snapshot.";
 if (market.status === "CURRENT") return ko ? "동일 날짜의 완전한 운영 추론을 확인할 수 없습니다. 현재 점수를 표시하지 않습니다." : "A complete same-date operational inference could not be verified. Current scores are unavailable.";
 if (ko && market.reason) return market.reason;
 if (market.status === "BLOCKED") {
  if (market.reason?.includes("불일치")) return "Historical source data do not reproduce the frozen feature reference. Current inference is withheld; historical results remain separate.";
  return ko ? "입력 또는 모델 검증이 통과되지 않아 신규 추론을 보류합니다." : "Input or model validation did not pass. Current inference is withheld.";
 }
 return ko ? "최신 필수 관측을 확인하지 못했습니다. 과거 점수를 현재로 이월하지 않습니다." : "Required current observations are not verified. Historical scores are not carried forward.";
}
