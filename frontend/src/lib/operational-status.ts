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
 if (currentOperationalPoint(market)) return ko ? "표시한 관측일의 필수 원천과 고정 모델 추론이 검증되었습니다. 평일마다 검증해 게시하는 스냅샷이며 실시간 자료는 아닙니다." : "Required sources and frozen model inference are verified for the displayed observation date. This is a validated daily snapshot, not a live feed.";
 if (market.status === "CURRENT") return ko ? "동일 날짜의 완전한 운영 추론을 확인할 수 없습니다. 현재 점수를 표시하지 않습니다." : "A complete same-date operational inference could not be verified. Current scores are unavailable.";
 if (ko && market.reason) return market.reason;
 if (market.status === "BLOCKED") {
  if (market.reason?.includes("불일치")) return "Historical source data do not reproduce the frozen feature reference. Current inference is withheld; historical results remain separate.";
  return ko ? "입력 또는 모델 검증이 통과되지 않아 신규 추론을 보류합니다." : "Input or model validation did not pass. Current inference is withheld.";
 }
 return ko ? "최신 필수 관측을 확인하지 못했습니다. 과거 점수를 현재로 이월하지 않습니다." : "Required current observations are not verified. Historical scores are not carried forward.";
}

// 운영 파이프라인이 한국어로만 남기는 진단 문구(trainingEvidence, reason)의 영어판. 새 문구가 생기면 여기에 더한다.
const pipelineEnglish: Record<string, string> = {
 "scaler 통계와 labeled 3714행 일치; 실행 시각 미기록": "Scaler statistics match the 3,714 labeled rows; run time not recorded",
 "6317행 prefix scaler 근사 일치; cutoff 추정, 정확한 학습 receipt 미보존": "Scaler approximately matches a 6,317-row prefix; cutoff estimated, exact training receipt not preserved",
 "일부 원천 수집 실패. 과거 캐시 재현 결과만 별도 표시합니다.": "Some sources failed to collect. Only results replayed from the historical cache are shown separately.",
 "최신 필수 원천 관측 미확인. 과거 재현 추론을 현재 점수로 이월하지 않습니다.": "Latest required source observations not confirmed. Historical replay inference is not carried over as the current score.",
};
export function pipelineText(value: string | null | undefined, language: Language): string | undefined {
 if (value == null || language === "ko") return value ?? undefined;
 if (pipelineEnglish[value]) return pipelineEnglish[value];
 const failed = /^수집 실패 \(([^)]+)\); 인증·네트워크·제공처 응답 확인 필요$/.exec(value);
 if (failed) return `Collection failed (${failed[1]}); check authentication, network and provider responses`;
 // 모르는 문구는 한국어 원문 대신 안내만 보여 준다(KR 화면에서 원문 확인).
 return /[가-힣]/.test(value) ? "Diagnostic recorded by the data pipeline in Korean; switch to KR to read the original." : value;
}

// 시장별 기준일: 실제로 점수를 표시하는 관측일(현재 점수, 없으면 마지막 유효 점수)과 지연 여부.
// 한국·미국은 거래일과 원천 공개 시점이 달라 하나의 날짜로 합치지 않는다.
export function marketAsOf(market?: OperationalMarketData | null): { date: string | null; expected: string | null; delayed: boolean } {
 const current = currentOperationalPoint(market);
 const shown = current ?? lastValidOperationalPoint(market);
 return { date: shown?.date ?? null, expected: market?.expectedDate ?? null, delayed: !current };
}
