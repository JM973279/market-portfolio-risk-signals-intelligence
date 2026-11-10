# Market Qualitative Signals

뉴스 원인 해석 같은 비정형·정성 정보를 Korea Market Stress 모델에 **어디까지, 어떤 방식으로** 반영할 수 있는지 실험하는 별도 저장소입니다.
AWS에 배포하는 `market-portfolio-risk-intelligence`와 분리되어 있고, 그 저장소는 **읽기만** 합니다.

## 원칙

1. **사후 뉴스 라벨은 모델 학습·튜닝에 쓰지 않습니다.** 해석·진단용 이벤트 레이어로만 씁니다.
2. 2026년 10월 홀드아웃 규칙(`market_engine/early_warning_v2/EXPERIMENTS.md`)을 따릅니다. 이 저장소의 결과를 보고 V1/V2 피처나 기준을 고르지 않습니다.
3. 모델 피처 후보가 되려면 과거 전 기간에 날짜 t 기준(point-in-time)으로 계산할 수 있어야 하고, 동결 V1 17개 피처 대비 purged walk-forward ablation을 통과해야 합니다.

## 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| ③ 이벤트 레이어 | 급락일·트리거 주석 + V1 사전 경보 진단 | **구현** |
| ① 정량 프록시 | 신용융자·예탁금, 외국인 순매수, 2종목 시총 비중, SOX, WTI → ablation | 예정 |
| ② 텍스트 지수 | 한국은행 뉴스심리지수(NSI), 일별 지정학 위험지수(GPR) → ablation | 예정 |

## 첫 결과 (2026-11-10 import 기준)

전체 표: [reports/event_diagnostics.md](reports/event_diagnostics.md)

- 뉴스 목록 10건 중 진단 가능한 9건: **스트레스 진행 중 추가 급락 6**, 사전 경보 있음 1(6/8), **사전 경보 없음 2(10/13, 10/15)**. 나머지 1건(11/6)은 점수 데이터가 11/2까지라 진단하지 못했습니다.
- 3/4 전쟁 급락 전날인 3/3(-7.92%, 뉴스 목록에 없음)에 V1은 직전 10거래일 내내 경보 상태였습니다. 트리거(전쟁)는 예측할 수 없어도 취약한 상태는 점수에 이미 나타나 있었던 사례입니다. 한 사례라 일반화하지는 않습니다.
- 경보가 빈 곳은 10월 AI·반도체 급락입니다. 급락 전 10거래일 최고 점수가 15.6%(10/13), 37.8%(10/15)로 경보 기준 50%에 못 미쳤고(동결 모델 사후 추론), 급락 당일 MSI도 Stress 기준 미만이었습니다.
- 2026년 KOSPI200 -5% 이하 하락일 22일 중 15일은 뉴스 목록에 없었습니다. 진단 대상은 뉴스가 아니라 가격 데이터로 골라야 합니다.

## 실행

표준 라이브러리만 씁니다(Python 3.10+). 호스트 `python3`로 바로 실행됩니다.

```bash
python3 -m qsignals.import_scores   # 배포 저장소 JSON → data/input/ (읽기 전용 복사, sha256 기록)
python3 -m qsignals.diagnose        # → reports/event_diagnostics.{csv,md}
python3 -m unittest discover -s tests -t .
```

배포 저장소 경로가 다르면 `--source-root PATH`를 넘깁니다. 11/6 이후 이벤트는 배포 저장소의 `operational-markets.json`이 갱신된 뒤 `import_scores`를 다시 실행하면 진단됩니다.

## 구조

```text
data/events/kospi_2026_events.csv   급락일 주석 (사람이 작성)
data/input/korea_scores.csv         V1 점수·MSI·KOSPI200 (import_scores가 생성)
data/input/provenance.json          출처 브랜치·커밋·sha256·행 수
qsignals/scores.py                  점수 시계열 병합·검증
qsignals/events.py                  이벤트 스키마·검증
qsignals/diagnostics.py             사전 경보 판정, 대형 하락일 스캔
qsignals/report.py                  CSV / 한국어 Markdown 출력
reports/                            진단 결과
```

점수 병합: walk-forward OOS(`global-markets.json`, ~2026-09-16)가 우선이고, 그 이후 날짜는 동결 모델(학습 기준일 2026-09-16)의 사후·운영 추론(`operational-markets.json`)으로 채웁니다. 행마다 `record_type`으로 구분합니다.

## 판정 기준 (고정)

- 경보: V1 Risk Score ≥ 0.50 (운영 기준 그대로)
- 스트레스 진행 중 추가 급락: 직전 5거래일 중 MSI ≥ 공식 Stress 기준인 날이 있음
- 사전 경보 있음: 위가 아니고, 직전 10거래일(Target_10D 기간) 중 경보가 하루 이상
- 사전 경보 없음: 둘 다 아님
- 급락 당일 점수는 당일 종가까지 반영하므로 '사전' 판정에서 뺍니다. 직전 구간에 결측이 있으면 판정하지 않습니다.

## 이벤트 CSV 작성 규칙

| 열 | 값 |
|---|---|
| `trigger_primary`, `trigger_secondary` | `geopolitics` 지정학, `macro_rates` 금리·물가·고용, `ai_semis` AI·반도체 사이클, `flows` 수급·차익실현, `politics_regulation` 정치·규제 |
| `amplifiers` | `;`로 구분. 아래 표의 정량 프록시와 연결됩니다 |
| `market_halt` | `CB`, `sidecar` (`;` 구분) |
| `source_quality` | `news`, `blog`, `mixed`, `unsourced` (`unsourced`이면 URL 없음) |
| `basis` | `post_hoc_news`: 나중에 정리한 사후 라벨 / `same_day_log`: 그날 장 마감 후 바로 기록 |

`same_day_log`로 매일 쌓으면 그 시점에 알 수 있던 정보만 담긴 텍스트 데이터가 됩니다. 몇 년 분량이 쌓여야 피처 후보가 될 수 있습니다.

## Amplifier → 정량 프록시 (① 후보)

| 메커니즘 | 프록시 (일별) | 출처 | 비고 |
|---|---|---|---|
| `margin_debt` | 신용거래융자 잔고, 투자자예탁금 | 금융투자협회 FreeSIS | |
| `foreign_selling`, `institutional_selling` | 코스피 투자자별 순매수 | KRX | |
| (구조) 2종목 쏠림 | 삼성전자+SK하이닉스 시총 비중 | KRX | |
| (전달) 미국 반도체 충격 | SOX 전일 수익률 | yfinance `^SOX` | |
| `oil_price` | WTI | FRED | |
| `krw_weakness` | USD/KRW | | Signal Divergence에서 이미 기각 (`signal_divergence/VALIDATION.md`) |
| `single_stock_leveraged_etf`, `hedge_fund_deleveraging`, `pension_rebalancing` | — | | 이력이 짧거나 공개 일별 데이터가 없어 제외 |

## 한계

- 트리거 라벨은 급락 이후 보도를 정리한 사후 해석입니다. 출처가 없는 이벤트도 있습니다.
- 보도 등락은 KOSPI, 데이터 수익률은 KOSPI200 기준입니다.
- 10월 점수는 walk-forward OOS가 아니라 동결 모델의 사후 추론입니다.
- 이 저장소는 모델을 바꾸지 않습니다. 모델 변경은 팀(A 트랙) 합의 후 배포 저장소에서 별도로 진행합니다.
