# Market & Portfolio Risk Intelligence (M/PRI)

한국·미국 시장의 스트레스 신호를 모니터링하고, 가상 포트폴리오의 **수익 기여도 · 벤치마크 대비 성과요인 · 비중 변경에 따른 위험**을 분석하는 AI 퀀트 과정 2차 프로젝트입니다.

*An interactive dashboard for Korea and US market stress monitoring, portfolio performance attribution, and risk analysis. Korean and English interfaces are available.*

**[포트폴리오 데모](https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/portfolio) · [시장 대시보드](https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/) · [10거래일 조기경보 백테스트](https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/validation) · [발표자료](https://jm973279.github.io/market-portfolio-risk-signals-intelligence/presentation/)**

## 담당 작업 · My contribution

- **포트폴리오 성과분석 웹/API**를 구현했습니다. 종목별 수익 기여도와 Brinson–Fachler 성과요인 합계를 각각 포트폴리오 수익률과 벤치마크 대비 초과수익에 맞춰 검증했습니다.
- 같은 기간·벤치마크에서 비중 변경 전후의 연율 변동성과 위험 기여도를 비교하는 기능을 구현했습니다. [구현 및 검증 기록 (PR #2)](https://github.com/JM973279/market-portfolio-risk-signals-intelligence/pull/2)

*I implemented the portfolio performance web app and API, tested return and benchmark attribution reconciliation, and added a like-for-like comparison of volatility and risk contributions after changing weights.*

## 대시보드에서 할 수 있는 일

| 화면 | 확인할 수 있는 내용 |
| --- | --- |
| [포트폴리오 분석](https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/portfolio) | 국내 주식·ETF의 과거 가상성과와 종목별 수익 기여도, KODEX 200 대비 성과요인을 확인합니다. 비중 변경 전후의 변동성·위험 기여도를 같은 조건에서 비교할 수 있습니다. 미국 달러 포트폴리오도 지원합니다. |
| [한국 시장](https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/korea) · [미국 시장](https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/us) | 시장 스트레스 지수(MSI)와 V1 위험 점수의 흐름을 확인합니다. 한국 화면에서는 시장 확산도와 신호 지속성도 살펴볼 수 있습니다. |
| [조기경보 백테스트](https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/validation) | 저장된 표본 외 예측으로 향후 10거래일 내 스트레스 경보를 평가합니다. 경보 기준을 조정하고 정밀도·재현율과 연도별 결과를 비교할 수 있습니다. |
| [급락 시나리오](https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/cases) | KOSPI 200과 SPY의 과거 급락 사례에서 낙폭, 직전 위험 점수, 사전 경보 여부를 비교합니다. |

## 검증과 해석

- **성과와 위험** — 과거 수정종가를 사용한 가상 포트폴리오입니다. 성과요인 합계는 벤치마크 대비 초과수익과 대사합니다. 실제 섹터별 성과요인에는 별도의 과거 벤치마크 구성·분류 자료가 필요합니다. [포트폴리오 계산 방법](docs/portfolio.md)
- **경보와 급락 사례** — 표본 외 백테스트와 동결 V1 모델의 사후·운영 추론을 구분합니다. 사후 뉴스 주석은 급락 해석에 사용합니다. [급락 진단 결과](reports/event_diagnostics.md) · [신호 실험](reports/signal_checks.md)
- **데이터 기준일** — 가격 관측일과 위험 추정일을 따로 표시합니다. GitHub Actions가 수집·검증한 스냅샷을 사용하고, 검증에 실패하면 마지막 검증본을 제공합니다. [데이터와 방법론](https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/sources)

## 관련 저장소

- [연구 코드](https://github.com/JM973279/market-portfolio-risk-intelligence) — 초기 시장 스트레스 모델 검증과 포트폴리오 위험 분석 연구
- [Docker 실행 도구](https://github.com/JM973279/market-portfolio-risk-dashboard-docker) — 연구용 원본을 로컬에서 실행하는 도구

## 로컬에서 실행

Next.js 웹과 Python 포트폴리오 API를 함께 실행합니다.

```bash
docker compose -f infra/aws/compose.yaml up --build
```

브라우저에서 [http://localhost:3300](http://localhost:3300)을 엽니다. [배포·데이터 갱신·재현 가이드](https://github.com/JM973279/market-portfolio-risk-signals-intelligence/blob/482788b8eb244ad3b942b3dc1ec2f7c61738eeac/README.md#전체-웹사이트-배포-awsdocker--이-저장소가-기준입니다)
