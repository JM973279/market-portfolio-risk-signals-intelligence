# 최신 데이터 N/A 진단 — 2026-10-29

## 결론

N/A는 저장된 정상 과거 값을 프런트엔드가 읽지 못해서 발생한 문제가 아니다.
현재 화면의 기준일 2026-10-27은 한국 breadth의 마지막 날짜다. 그 날짜의
V1 추론 결과와 공식 MSI/임계값은 연결된 입력에 없다. 날짜를 정확히 결합하고
과거 점수를 이월하지 않으므로 한국 최종 상태 UNKNOWN은 올바른 결과다.
미국 개요 카드도 동일한 스냅샷 날짜를 정확히 조회한다. 미국의 마지막 저장
관측일은 더 이르므로 해당 날짜의 현재 지표는 N/A다.

이번 작업은 파일·코드 읽기 및 테스트만 수행했다. 수집기, 추론 API, feature/MSI
생성기, walk-forward 학습기는 실행하지 않았으며 모델이나 점수를 생성하지 않았다.

## 마지막 이용 가능 관측

모든 날짜는 로컬 파일의 실제 행/비결측값을 확인한 결과다. 최신 거래일이나
외부 제공처의 현재 서비스 상태를 검증했다는 의미는 아니다.

| 항목 | 한국 | 미국 — 별도 기존 V1 프로젝트 |
| --- | --- | --- |
| 저장된 V1 10D OOS Risk Score | 2026-09-16, 2,454행 | 2026-09-21, 5,060행 |
| 통합 특징 파일의 MSI | 2026-10-02 | 2026-10-05 |
| 통합 특징 파일의 공식 임계값 | 2026-10-02 | 2026-10-05 |
| Risk/MSI/임계값 동시 존재 마지막 날짜 | 2026-09-16; 한국 breadth도 완전 | 2026-09-21; 한국 breadth 규칙 적용 안 함 |
| 별도 추론용 feature 파일 | 2026-10-15, 4,070행 | 2026-10-05, 6,669행 |
| breadth | 2026-10-27 | 검증·연결된 미국 탐지기 없음 |
| 한국 보조 확인용 cross-asset 파일 | 2026-10-02 | 미국 독립 탐지기로 사용하지 않음 |

한국 `korea_latest_features_v1_reproduction.csv`는 17개 모델 feature와 원천
가격/변동성/신용 값은 포함하지만 MSI, 공식 임계값, Risk Score는 포함하지 않는다.
따라서 이 파일의 존재만으로 현재 모니터링 상태를 계산할 수 없다.

## 정상 과거 값과 결측 확인

| 시장 / 날짜 | Risk Score 표시값 | MSI | 공식 임계값 | 해석 |
| --- | --- | --- | --- | --- |
| 한국 2026-09-16 | 6.4% (원본 0.06390466541051865) | 0.3988964075 | 1.1168414930 | 기존 저장값 정상; 최종 상태 NORMAL |
| 한국 2026-10-02 | N/A | 0.2224127766 | 1.1160679657 | MSI/임계값은 존재하나 OOS 점수 없음 |
| 한국 2026-10-27 | N/A | N/A | N/A | breadth는 존재하지만 필수 입력 없음 → UNKNOWN |
| 미국 2026-09-21 | 11.1% (원본 0.11131133139133453) | -1.2746392426 | 1.2927670744 | 기존 V1의 정상 과거 OOS 기록 |
| 미국 2026-10-05 | N/A | -0.7980418108 | 1.2925234839 | 가격/관측 스트레스만 존재; OOS 점수 없음 |
| 미국 2026-10-27 | N/A | N/A | N/A | 연결된 미국 시계열에 해당 날짜의 행 자체가 없음 |

한국 화면의 ‘마지막 완전 관측’ 버튼 또는 날짜 선택기로 9월 16일의 정상
Risk/MSI/임계값을 확인할 수 있다. 미국은 `/us`의 과거 OOS 요약 및 차트 관측
슬라이더에서 9월 21일을 확인할 수 있다. 과거 값은 현재 점수로 취급하지 않는다.

## 단계별 원인

### 1. 수집과 원천 데이터의 종료일이 다르다

별도 기존 V1 저장소의 한국 KRX(KOSPI/KOSPI200), VKOSPI, ECOS 신용 CSV는
2026-10-15까지 있다. 한국 breadth는 다른 수집 경로로 10월 27일까지 있다.
원천 한국 지수 파일은 날짜당 여러 Index 행을 가진 long format이며
`(Date, Index)` 중복은 0이다. 날짜만 중복되는 것은 오류가 아니다.

미국 `data/raw/raw_market_data.csv`의 SPY/VIX는 2026-10-05까지,
BAA-Treasury Spread의 마지막 실제 비결측 원천 관측은 2026-10-02다.
기존 `src/data/cleaner.py`는 VIX/신용에 최대 5행의 과거값 이월을 사용한다.
따라서 저장된 10월 5일 MSI는 원래 전처리 정책을 상속한 파생 기록이지,
세 채널이 모두 10월 5일 새로 관측되었다는 증거는 아니다.
이번 프런트엔드나 진단은 값을 새로 이월하지 않았고 기존 기록도 변경하지 않았다.

이 조사로 저장 파일의 종료일은 확인했지만 외부 제공처의 수집 실패 원인,
스케줄러 실행 기록, 네트워크/인증 상태는 확인하지 않았다. 서비스 장애나
API 키 오류를 N/A의 확정 원인으로 주장할 근거는 없다.

### 2. 한국 공식 MSI/target과 추론용 feature의 갱신 범위가 분리되어 있다

- 기존 V1의 `data/processed/korea/korea_stress_index.csv`와
  `korea_targets.csv`는 10월 2일에 끝난다.
- 현재 프로젝트의 `market_engine/early_warning_v2/build_korea_features_v2.py`는
  원천 자료로 별도 추론 feature를 만들지만, 연구 matrix에는 공식 target 파일을
  **inner join**한다. 따라서 공식 MSI/target 종료일 이후의 행은 그 matrix에 없다.
- 해당 빌더의 `inference_only=True` 경로는 추론 feature만 저장하고 공식 target
  join 전에 반환한다. 10월 15일 추론 feature와 10월 2일 연구 matrix의 공존은
  코드의 분리된 출력 구조와 일치한다. 실제 실행 이력을 단정할 로그는 없다.
- 두 시장의 연구 matrix에서 마지막 10개 거래 관측의 `Target_10D`는 아직
  미래 결과가 관측되지 않아 비어 있다. 한국의 마지막 유효 label은 9월 16일,
  미국은 9월 21일이다.

### 3. OOS 검증 기록은 최신 추론 기록이 아니다

`market_engine/early_warning_v2/korea_walk_forward_v2.py`는 유효한
`Target_10D` 행만 OOS 평가에 사용한다. 따라서 OOS 점수가 마지막 feature 날짜보다
10개 거래 관측 뒤처지는 현상은 미래 label을 요구하는 검증 절차와 일치한다.
미국 원본 multi-horizon 검증도 같은 구분을 사용한다.

현재 웹사이트는 OOS CSV를 읽으며 그 이후의 고정 모델 추론 결과를 제공하는
입력을 연결하지 않았다. **현재 추론 자체에는 미래 target label이 필요하지 않다.**
최신 점수를 만들기 위해 학습기를 다시 실행하거나 미래 target 결측을 0으로
채우면 안 된다. 특히 현재 walk-forward 스크립트는 학습 및 모델 저장을 수행하므로
단순 갱신 명령으로 제안하지 않는다.

별도 기존 V1 API 코드에는 `/api/latest`, `/api/korea/latest`와 저장 모델을
사용하는 추론 함수가 있지만, 이 사이트는 이를 호출하지 않는다. 이번 조사에서도
추론이 발생할 수 있는 endpoint는 호출하지 않았다. 외부 API/운영 상태와 모델의
학습 cutoff·feature 순서·입력 신선도를 검증하기 전에는 직접 연결하지 않는다.

### 4. 날짜 결합과 결측 처리는 의도대로 작동한다

`market_engine/signal_divergence/monitor.py`는 실제 V1/MSI/breadth 관측일의
합집합에 exact-date, one-to-one join을 수행한다. 모니터 입력의 날짜는 중복되지
않으며 불완전한 3회 breadth 구간은 미확인으로 유지한다. 필수 V1/MSI/공식
임계값/지속성 중 하나라도 없으면 UNKNOWN이다. 상관 결측은 이 상태를
정상으로 바꾸거나 breadth 판정을 덮어쓰지 않는다.

### 5. 프런트엔드는 정적 연구 스냅샷을 정확히 표시한다

- `frontend/public/data/korea-monitor.json`은 원천 관측 종료일과 실제 결측을 보존한다.
- `frontend/scripts/prepare-dashboard-data.py`는 별도 미국 V1 파일을 읽고 기존
  한국 export에서 표시용 `global-markets.json`을 만든다. 모델을 실행하지 않는다.
- 그 스냅샷의 `asOf`는 한국 최신 breadth 관측일 2026-10-27이다.
- `frontend/src/components/research-panels.tsx`의 개요 카드는 미국도 이 날짜의
  행을 정확히 찾는다. 10월 5일의 MSI를 10월 27일 값으로 가져오지 않는다.
- `frontend/src/lib/dashboard-data.ts`는 `use cache`로 로컬 JSON을 읽는다.
  자동 API 호출이나 예약 갱신이 없으므로 CSV만 갱신해도 화면이 최신화되지 않는다.
  검증된 export 생성과 새 build/restart 또는 명시적 캐시 무효화가 필요하다.

## 추가 수정이 필요한 위치와 우선순위

아래는 **제안**이며 이번 작업에서는 구현·수집·추론을 수행하지 않았다.
기존 V1 프로젝트와 연구 결과를 보존하는 별도 운영 경로로 진행해야 한다.

| 우선순위 | 필요한 작업 | 대상 파일/신규 경계 |
| --- | --- | --- |
| P0 | 한국 지수·VKOSPI·신용과 미국 SPY·VIX·신용의 수집 receipt, 실제 관측일, retrieval 시각, 거래소 달력 확인 | 별도 read-only 수집 adapter/상태 manifest; 기존 V1 수집·정제 코드 참조 |
| P0 | 한국 공식 MSI와 날짜별 임계값을 기존 공식 방식 그대로 갱신·검증한 별도 운영 export 준비; 과거 행 해시 보존 | 기존 `src/korea/build_korea_stress_index.py`, `build_korea_target.py`의 명세 참조; 현재 프로젝트에 별도 adapter 추가 |
| P1 | 모델 artifact hash, 학습 cutoff, 17개 feature 순서와 당일 입력을 검증한 **고정 V1 추론 전용** 경로 설계; OOS와 별도 저장 | 새 inference 전용 모듈. `build_korea_features_v2.py`의 입력 경로/운영 출력을 검토하되 연구 matrix·학습기를 덮어쓰지 않음 |
| P1 | 운영 V1/MSI snapshot을 기존 OOS 및 실험적 Korea divergence 출력과 명시적으로 분리 | 새 exporter와 schema. `monitor.py`/기존 OOS 파일을 임의 재작성하지 않음 |
| P2 | 검증된 source별 관측일·운영 상태를 표시하고 ‘마지막 개별 MSI’와 ‘스냅샷 날짜의 현재 MSI’를 구분 | `frontend/scripts/prepare-dashboard-data.py`, `src/lib/dashboard-types.ts`, `src/components/research-panels.tsx`, `src/lib/dashboard-copy.ts` |
| P2 | 검증 완료된 export의 원자적 배포와 명시적 재검증/캐시 무효화 연결 | `src/lib/dashboard-data.ts`, 배포/갱신 작업 정의 |

원천 자료와 공식 MSI가 없는 10월 27일의 Risk/MSI를 프런트엔드 수정만으로 복원할
수는 없다. 과거 값을 별도 날짜와 함께 더 잘 보여주는 것은 가능하지만 그것을
현재 점수나 검증된 실시간 예측으로 표시하지 않는다.

## 이번 게시 전 검증

Production build, standalone TypeScript, ESLint, chart helper 검증이 모두 통과했고
Python 연구/스냅샷 테스트는 16개가 통과했다. 새 모델·원천 데이터·기존 실험 결과를
게시 변경에 추가하지 않는다. 최초 보존 기준의 연구/export/model 파일 162개
SHA-256이 그대로다. 웹 표시용 JSON 2개(약 2.28 MB, 1.61 MB), 로컬 폰트,
헤더 이미지는 웹사이트 재현을 위한 의도된 파일이다.
