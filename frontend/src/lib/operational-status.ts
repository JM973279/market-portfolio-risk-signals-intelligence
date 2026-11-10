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

// 점수·MSI·임계값이 모두 유한한 숫자이고 Risk가 0~1 범위인지 확인한다.
function validPoint(point: OperationalPoint | null | undefined): point is OperationalPoint {
 if (!point) return false;
 if (![point.risk, point.msi, point.threshold].every(value => typeof value === "number" && Number.isFinite(value))) return false;
 return point.risk! >= 0 && point.risk! <= 1;
}

// A past record is never a fallback for a missing or blocked current observation.
export function currentOperationalPoint(market?: OperationalMarketData | null): OperationalPoint | null {
 const point = market?.current;
 if (market?.status !== "CURRENT" || !point || point.date !== market.expectedDate) return null;
 return validPoint(point) ? point : null;
}

// 마지막 유효 점수 (시장 카드 전용 표시)
// - 현재 점수가 없을 때만 쓴다. 예: 미국이 DELAYED인 경우. FRED 신용 금리(DBAA/DGS10)가
//   기대 관측일보다 늦게 공개되어 11/09 점수는 없고, 11/06 점수만 검증되어 있다.
// - 이 값은 현재 점수가 아니다. currentOperationalPoint와 상태(status)·안내 문구는 그대로
//   "최신 점수 미확인"으로 두고, 카드에는 "마지막 유효 점수 · 날짜"를 붙여 따로 보여 준다.
// - export의 lastValid는 동결 모델이 실제 관측일에 계산한 추론 기록이다(가격 제외).
//   현재 점수가 있으면(CURRENT) null을 돌려 현재 점수만 표시한다.
export function lastValidOperationalPoint(market?: OperationalMarketData | null): OperationalPoint | null {
 if (!market || currentOperationalPoint(market)) return null;
 const point = market.lastValid;
 return point?.date && validPoint(point) ? point : null;
}

// 자료가 늦을 때 값 아래에 붙이는 주석
// - 최신 자료가 아직 안 들어와 마지막 유효 점수를 대신 보여 줄 때만 문장을 돌려준다(그 외 null).
// - 기대 관측일, 실제로 표시한 날짜, 기대 관측일보다 늦은 원천(관측일 포함)을 적는다.
//   예: "기대 관측일 2026-11-09 자료가 아직 들어오지 않아 2026-11-06 점수를 표시했습니다.
//        늦은 원천: DBAA 2026-11-06 · DGS10 2026-11-06. 현재 점수로 이월한 값이 아닙니다."
export function staleScoreNote(market: OperationalMarketData | null | undefined, language: Language): string | null {
 const point = lastValidOperationalPoint(market);
 if (!market || !point) return null;
 const ko = language === "ko";
 const expected = market.expectedDate;
 const late = market.series
  .filter(source => source.status === "ERROR" || !source.observationDate || (expected && source.observationDate < expected))
  .map(source => `${source.name} ${source.observationDate ?? (ko ? "없음" : "none")}`);
 const lateText = late.length ? (ko ? ` 늦은 원천: ${late.join(" · ")}.` : ` Late sources: ${late.join(" · ")}.`) : "";
 return ko
  ? `※ 기대 관측일 ${expected ?? "N/A"} 자료가 아직 들어오지 않아 ${point.date} 점수를 표시했습니다.${lateText} 현재 점수로 이월한 값이 아닙니다.`
  : `※ Data for the due date ${expected ?? "N/A"} has not arrived, so the ${point.date} score is shown.${lateText} It is not carried forward as the current score.`;
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
