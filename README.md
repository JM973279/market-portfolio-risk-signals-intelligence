# Market Qualitative Signals

뉴스 원인 해석 같은 비정형·정성 정보를 Korea Market Stress 모델에 **어디까지, 어떤 방식으로** 반영할 수 있는지 실험하는 별도 저장소입니다.
AWS에 배포하는 `market-portfolio-risk-intelligence`와 분리되어 있고, 그 저장소는 **읽기만** 합니다.

## 서버 주소 (배포된 최신 화면)

| 화면 | 주소 |
|---|---|
| 전체 사이트 (대시보드·백테스팅 테스트·시나리오 분석·포트폴리오 분석) | **https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com** |
| 포트폴리오 분석 | https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/portfolio-lab |

AWS Lightsail 컨테이너 서비스 `mpri`(서울, `ap-northeast-2`)에 `release/latest-site-docker` 브랜치를 배포한 주소입니다. 아래의 `localhost` 주소는 내 PC에서 직접 실행할 때만 열립니다.

## 포트폴리오 성과·벤치마크 요인분해

이 저장소에서 실행하는 독립 웹/API를 추가했습니다. 기존 한국 이벤트 진단과 함께 사용할 수 있습니다.

```bash
python3 -m qsignals.portfolio_server
# http://127.0.0.1:3108/portfolio
```

### Docker로 실행 (다른 사람과 공유하기 쉬움)

Dockerfile과 docker-compose가 포함되어 있습니다. 서버는 표준 라이브러리만 사용하며 데이터는 이미지에 포함됩니다.

```bash
# 로컬 빌드·실행
docker compose up --build
# 또는
docker build -t market-portfolio-risk .
docker run -p 3108:3108 market-portfolio-risk
```

브라우저에서 **http://localhost:3108/portfolio** 로 접속하세요.

GitHub Actions가 main 브랜치 푸시 시 자동으로 [GitHub Container Registry](https://ghcr.io)에 이미지를 퍼블리시합니다.

```bash
docker pull ghcr.io/jm973279/market-portfolio-risk-signals-intelligence:latest
docker run -p 3108:3108 ghcr.io/jm973279/market-portfolio-risk-signals-intelligence:latest
```

다른 사람에게 공유할 때는 위 [서버 주소](#서버-주소-배포된-최신-화면)의 공개 주소를 보내세요.

종목·비중을 입력하면 과거 가상성과, 종목별 수익 기여도, 벤치마크 대비 자산배분·선택·상호작용 효과, 별도 위험 추정, 비중 변경 비교를 제공합니다. SPY·주식/국채 60:40·사용자 지정 기준을 지원합니다. 실제 섹터별 종목선택 분석은 과거 구성·분류·수익률 자료가 연결된 기간에만 제공하며 현재 기본 자료는 미연결 상태입니다.

데이터는 GitHub Actions가 전체 수정종가·금리를 수집·검증해 저장한 스냅샷을 읽습니다. 원본 저장소·ref는 유지하고, 가격 최신일과 금리가 필요한 위험 추정일을 구분합니다. 수집 시각을 최신 가격일로 표시하지 않으며 실제 가격 종료일은 화면과 `data/portfolio/current.json`에서 확인합니다. [실행·데이터 연결·계산 규칙](docs/portfolio.md), [검증 및 자동 갱신 workflow](.github/workflows/refresh-portfolio.yml).

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

## 진단 결과와 데이터 갱신

전체 표: [reports/event_diagnostics.md](reports/event_diagnostics.md)

- 수치와 실제 관측 종료일은 보고서에서 확인하세요. 점수와 가격의 마지막 날짜를 각각 표시하며 README에 결과 수치를 중복 고정하지 않습니다.
- 기본 입력은 공개 원본 `tina77302/market-portfolio-risk-intelligence`의 main을 조회한 뒤 **한 커밋으로 고정**한 두 JSON입니다. 오래된 로컬 worktree를 자동 선택하지 않습니다. `--source-repo`로 출처를 변경할 수 있습니다.
- 원본에 없는 가격은 Naver Finance `KPI200` 일봉으로 보충합니다. 동결 KOSPI200 종가와 5거래일 이상 겹쳐 확인하고, 차이가 0.005포인트를 넘으면 발행을 중단합니다. 2026-11-10 복구 시 겹친 475거래일 종가는 모두 일치했습니다.
- 보충 가격은 사건 수익률·누락 급락일 조사에만 사용하며 Risk Score·MSI·공식 기준값·모델은 바꾸지 않습니다.
- 11/6 사건은 최신 점수 연결 후 ‘데이터 없음’에서 ‘사전 경보 없음’으로 진단되었습니다. 동결 모델의 사후·운영 추론에 대한 진단이며 새 OOS 검증이 아닙니다.
- 가격만 있는 날짜는 `NO_SCORE`로 유지합니다. 과거 점수를 복사해 현재 점수로 표시하지 않습니다.

## 자동 갱신

[Refresh Korea event diagnostics](https://github.com/JM973279/market-portfolio-risk-signals-intelligence/actions/workflows/refresh-diagnostics.yml)는 **4시간마다** 공개 원본 점수와 공개 가격을 확인하며 수동 실행도 가능합니다. GitHub 예약 실행은 지연될 수 있습니다.

추가 API 키 없이 실행하고, main에서 수집·검사·보고서 생성이 성공하면 입력과 보고서를 커밋합니다. 조회나 일치 검증이 실패하면 마지막 검증 파일을 덮어쓰지 않습니다. 같은 입력으로 불필요한 타임스탬프 변경 커밋을 만들지 않습니다. 보고서는 원천의 과거 `CURRENT` 문자열을 그대로 믿지 않고 실행 시점의 기대 거래일과 실제 관측일을 비교합니다.

## 실행

표준 라이브러리만 씁니다(Python 3.10+). 호스트 `python3`로 바로 실행됩니다.

```bash
python3 -m qsignals.import_scores   # 공개 원본 main을 한 커밋으로 고정 + KOSPI200 일봉 검증
python3 -m qsignals.import_scores --source-root /path/to/checkout  # 명시적 로컬 입력
python3 -m qsignals.diagnose        # → reports/event_diagnostics.{csv,md}
python3 -m unittest discover -s tests -t .
```

재현 시 `--source-ref COMMIT_SHA`로 원본을 고정합니다. `--price-replay data/input/provenance.json`은 보존한 가격 원응답을 해시 검증해 재사용합니다. 완전한 오프라인 재현은 해당 커밋의 로컬 체크아웃을 `--source-root`로 함께 넘깁니다.

달력은 `data/calendar/`에 해시와 출처를 기록했습니다. exchange_calendars 4.13.2의 XKRX에 2026-06-03·07-17 추가 휴장을 반영했고 2016~2026년을 지원합니다. 지원 기간 밖 자료를 처리하려면 달력을 명시적으로 갱신해야 합니다. 핵심 코드와 검사는 Python 표준 라이브러리만 사용합니다.

## 구조

```text
data/events/kospi_2026_events.csv   급락일 주석 (사람이 작성)
data/input/korea_scores.csv         V1 점수·MSI·KOSPI200 (import_scores가 생성)
data/input/provenance.json          출처 커밋·sha256·가격/점수 종료일·누락 거래일
data/input/kospi200_naver.xml        가격 제공처 원응답 (재현용)
data/calendar/                     KRX 거래일 달력·추가 휴장 출처
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
- 급락 당일 점수는 당일 종가까지 반영하므로 '사전' 판정에서 빡니다. 직전 구간에 행 전체가 빠진 경우까지 결측으로 처리합니다. 직전 거래일 가격이 없으면 여러 거래일 누적 등락을 일간 등락으로 계산하지 않습니다.

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

## 복구 검증 (2026-11-10)

- 원본 커밋과 두 JSON의 SHA-256, 보충 가격 원응답의 SHA-256, 생성 CSV의 SHA-256을 기록합니다.
- 같은 날짜의 기존 2,483개 Risk Score·MSI·공식 기준값·기록 유형은 복구 전후 일치합니다.
- 불가능한 날짜, 중복 날짜, NaN/무한값, 잘못된 종목 응답, 빠진 거래일, 가격 기준 불일치, 갱신 실패 시 파일 보존을 회귀 검사합니다.
- 출처가 없는 뉴스 주석 두 건은 보고서에서도 ‘출처 미확인’으로 표시합니다. 기존 뉴스의 인과 해석을 새로 검증했다는 의미는 아닙니다.
