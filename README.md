# Market Qualitative Signals

뉴스 원인 해석 같은 비정형·정성 정보를 Korea Market Stress 모델에 **어디까지, 어떤 방식으로** 반영할 수 있는지 실험하는 별도 저장소입니다.
AWS에 배포하는 `market-portfolio-risk-intelligence`와 분리되어 있고, 그 저장소는 **읽기만** 합니다.

## 서버 주소 (배포된 최신 화면)

| 화면 | 주소 |
|---|---|
| 전체 사이트 (대시보드·백테스팅 테스트·시나리오 분석·포트폴리오 분석) | **https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com** |
| 포트폴리오 분석 | https://mpri.hbgma4wzzydww.ap-northeast-2.cs.amazonlightsail.com/portfolio-lab |

AWS Lightsail 컨테이너 서비스 `mpri`(서울, `ap-northeast-2`)에 배포한 주소입니다. 아래의 `localhost` 주소는 내 PC에서 직접 실행할 때만 열립니다.

## 전체 웹사이트 배포 (AWS·Docker) — 이 저장소가 기준입니다

M/PRI 웹사이트(대시보드·백테스팅 테스트·시나리오 분석·포트폴리오 분석)의 최신 화면은 이 저장소의 `frontend/`에 있습니다. `tina77302/market-portfolio-risk-intelligence`나 PC에 남아 있는 예전 복사본은 구버전입니다.

`release/latest-site-docker`는 `main`에 병합되었습니다(PR #7). 이제 `main`에 전체 사이트(`frontend/`), `infra/aws/`, 포트폴리오 서버, 진단, KR/EN 화면, 예약 데이터 갱신 workflow가 모두 들어 있습니다.

```bash
# 웹(Next.js)과 포트폴리오 서버를 함께 실행
docker compose -f infra/aws/compose.yaml up --build
# http://localhost:3300
```

AWS Lightsail 배포는 `infra/aws/deploy_lightsail.sh`를 사용합니다(서비스를 처음 만들 때는 `CREATE_SERVICE=yes`, 월 과금 시작). 데이터는 빌드할 때 이미지에 들어가므로, GitHub Actions가 갱신한 데이터를 배포 화면에 반영하려면 최신 `main`으로 다시 빌드·배포해야 합니다. 배포 후 다음이 보이면 최신 버전입니다.

- 메뉴에 `백테스팅 테스트`와 `시나리오 분석`이 있습니다.
- 왼쪽 아래 `EN`을 누르면 포트폴리오 분석 화면까지 모든 글과 표시가 영어로 바뀝니다.

아래의 루트 `Dockerfile`·`docker-compose.yml`은 포트폴리오 서버(`/portfolio`)만 실행합니다.

## 화면 언어 (KR / EN)

사이트 왼쪽 아래 `KR`/`EN` 토글로 언어를 바꿉니다. 선택은 브라우저 탭(sessionStorage)에 기억됩니다.

- **사이트 문구**는 `frontend/src/lib/dashboard-copy.ts`, `monitor-copy.ts`에 `[영어, 한국어]` 쌍으로 있습니다.
- **포트폴리오 분석**(iframe)은 EN일 때 `/portfolio-lab?lang=en`으로 열립니다. 단독 실행 화면은 `http://127.0.0.1:3108/portfolio?lang=en`이며, 오른쪽 위 링크로도 바꿀 수 있습니다.
- **포트폴리오 API**는 `/api/portfolio/*?lang=en`으로 부르면 같은 계산 결과에 안내·오류 문구만 영어로 돌려줍니다. 영어판은 `qsignals/portfolio_i18n.py`에 있습니다.
- **운영 파이프라인 진단 문구**(`trainingEvidence`, `reason`)는 원천이 한국어로만 남깁니다. 영어판은 `frontend/src/lib/operational-status.ts`의 `pipelineText`에 있고, 모르는 문구는 EN 화면에서 "KR에서 원문 확인" 안내로 대신 보여 줍니다.
- 포트폴리오 코드에 한국어 문구를 새로 넣으면 `qsignals/portfolio_i18n.py`에 영어판도 넣으세요. 빠지면 `tests/test_portfolio_i18n.py`가 실패합니다.

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
| ① 개장 전 미국 가격 | EWY·SOX 전일 미국 세션 → 동결 V1 위 사전 등록 overlay 실험 | **구현** (Actions 첫 수집 후 판정) |
| ① MSI 인정 진단 | 공식 MSI가 대형 하락일을 스트레스로 인정했는지, 놓친 이유 | **구현** (진단 전용) |
| ② 개장 전 뉴스 기록 | 08:30 KST 이전 기록만 받는 실시간 누적 로그 | **구현** (기록 대기) |
| 표시 | 예정된 미국 발표(FOMC·CPI·고용·선거) 일정표 | **구현** (점수 미사용) |
| ① 정량 프록시 | 신용융자·예탁금, 외국인 순매수, 2종목 시총 비중, WTI → ablation | 예정 |
| ② 텍스트 지수 | 한국은행 뉴스심리지수(NSI), 일별 지정학 위험지수(GPR) → ablation | 예정 |

## 신호 보강 점검 (사전 등록)

결과: [reports/signal_checks.md](reports/signal_checks.md). 규칙은 코드 상수로 먼저 고정했고 결과를 보고 바꾸지 않습니다. 설계 구간은 2025-12-31까지, 2026년은 보고만 하는 홀드아웃입니다.

| 항목 | 무엇을 | 판정 규칙 | 모델 영향 |
|---|---|---|---|
| 개장 전 미국 가격 | KRX t+1일 개장 전에 끝난 미국 세션의 EWY·SOX 수익률을 V1(t)과 당일 KOSPI200 수익률에 더함 | 다음 거래일 −2% 이하 라벨에서 PR-AUC 개선의 월 블록 부트스트랩 95% 구간이 0 초과면 '후보' | 없음. 후보는 배포 저장소에서 17개 피처 ablation으로 재검증 |
| MSI 인정 진단 | 하루 −3% 이하 급락일에 공식 MSI ≥ 기준이었는지, 놓친 날의 21일 랠리 상쇄, 1년 고점 대비 낙폭 채널 | 설계 구간에서 놓침 ≥30%, 보강 채널 회수 ≥50%, 전체 표시 ≤15%면 'MSI 개정 제안 근거' | 없음. 공식 MSI·라벨은 동결 |
| 개장 전 뉴스 기록 | `data/events/preopen_log.csv`, 직전 거래일 15:30~당일 08:30 KST에 기록한 행만 허용 | 분류자별 250거래일·하락일 10일 이후에만 평가, 위험 회피 표시 연 5회 이하 | 없음. 사후 백필은 검증에서 거부 |
| 예정 발표 일정표 | `data/events/scheduled_us_2026.csv`, 발표일 다음 KRX 거래일에 표시 | 표시 전용 | 없음 |

개장 전 가격은 외부 조회라 `Refresh overnight US prices` workflow의 격리 venv에서만 수집하고(`AGENTS.md`), 보고서·검사는 저장된 CSV와 sha256 provenance만 읽습니다. 제공처 결측 종가는 비워 두고 채우지 않습니다.

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
python3 -m qsignals.signal_checks   # → reports/signal_checks.md
python3 -m unittest discover -s tests -t .
```

재현 시 `--source-ref COMMIT_SHA`로 원본을 고정합니다. `--price-replay data/input/provenance.json`은 보존한 가격 원응답을 해시 검증해 재사용합니다. 완전한 오프라인 재현은 해당 커밋의 로컬 체크아웃을 `--source-root`로 함께 넘깁니다.

달력은 `data/calendar/`에 해시와 출처를 기록했습니다. exchange_calendars 4.13.2의 XKRX에 2026-06-03·07-17 추가 휴장을 반영했고 2016~2026년을 지원합니다. 지원 기간 밖 자료를 처리하려면 달력을 명시적으로 갱신해야 합니다. 핵심 코드와 검사는 Python 표준 라이브러리만 사용합니다.

배포 저장소 경로가 다르면 `--source-root PATH`를 넘깁니다.

**Windows에서 직접 실행할 때:** 저장소를 긴 경로에 두면 Windows 경로 길이 제한(260자)에 걸려 `data/portfolio/snapshots/...` 파일을 못 읽습니다. 또 기본 인코딩(cp949) 때문에 JSON 읽기가 실패할 수 있습니다. 짧은 경로에 clone하고 `git config core.longpaths true`, `git config core.autocrlf false`(해시 검증용 LF 유지), `PYTHONUTF8=1`을 쓰거나 WSL·Docker에서 실행하세요.

## 선택: 동결 파이프라인 직접 실행 (`qsignals.refresh`)

기본 운영 경로는 위의 GitHub 고정 export import입니다(`AGENTS.md`). 아래는 명시적으로 실행할 때만 쓰는 추가 경로이며, 같은 `import_data`(달력·KOSPI200 가격 대조)를 거쳐 저장합니다.

`import_scores`는 배포 저장소에 이미 있는 JSON만 복사합니다. 배포 저장소의 운영 export는 사람이 수집을 돌릴 때만 갱신되므로(자동 예약 없음), 그 JSON만 보면 점수가 멈춘 날짜에서 더 나아가지 않습니다. `qsignals.refresh`는 배포 저장소의 동결 파이프라인(`market_engine/operations/run.py --collect`)을 **수정 없이** 임시 사본에서 돌려 최신 한국·미국 점수를 직접 받아옵니다.

```bash
scripts/setup_inference_env.sh      # 최초 1회: ~/.venvs/mpri-inference (배포 저장소의 고정 버전)
python3 -m qsignals.refresh         # 수집 → 동결 모델 추론 → data/input/ 갱신
python3 -m qsignals.diagnose
```

- **배포 저장소와 원본 V1 저장소는 읽기만 합니다.** 둘 다 `git archive`로 `~/.cache/qsignals/runs/<시각>/`에 사본을 만들어 그 안에서 실행합니다. 배포 저장소의 `operational-markets.json`, 웹사이트, AWS 배포는 바뀌지 않습니다.
- **원본 V1 버전은 contract.json으로 고릅니다.** 파이프라인은 V1 소스 10개의 SHA-256이 맞아야 돕니다. V1 작업 폴더가 다른 브랜치(예: `feature/zscore-warning`)에 있어도, 모든 브랜치에서 해시가 맞는 커밋을 찾아 그 커밋으로 사본을 만듭니다. 맞는 커밋이 없으면 멈춥니다.
- **한국 원천 이력은 `~/.cache/qsignals/v1-data/raw/korea/`에 둡니다.** V1에서 gitignore된 파일이라 저장소에 없습니다. 첫 실행은 V1 다운로더로 2010년부터 받고(KRX 약 8,800회 호출), 이후에는 새 거래일만 받습니다.
- **한국 기준 행렬은 다시 만들어 검증한 뒤 씁니다.** 파이프라인은 새 feature를 `korea_feature_matrix_v1_reproduction.csv`와 대조하는데, 이 파일은 배포 저장소에서 gitignore되어 처음 만든 PC에만 있습니다. 사본에 원본이 없으면 같은 코드(V1 MSI·target 빌더 + 배포 저장소 feature 빌더)로 원천 이력을 2026-10-02에서 잘라 다시 만들고(`qsignals/_reference_worker.py`), 배포 저장소에 커밋된 근거와 대조합니다: ① `global-markets.json`의 한국 MSI·임계값 2,464일과 1e-9 이내 일치 ② 동결 모델 출력이 커밋된 `operational-markets.json` 점수와 일치(2026-11-10 기준 29일, 차이 0). 통과하면 `~/.cache/qsignals/reference/`에 두고 **임시 사본의** `contract.json` 기준 해시만 새 파일 해시로 바꿉니다. 원본과 바이트가 달라(SHA-256 `9fad15f4…` → `de2a5e6f…`) `provenance.json`의 `refresh.korea_reference`에 두 해시와 검증 결과를 남깁니다. 원본 파일이 사본에 있으면 원본을 씁니다.
- **기록 유형:** 배포 파이프라인은 원천 캐시 마지막 날 이후를 `OPERATIONAL`, 그 이전을 `RETROSPECTIVE_INFERENCE`로 표시합니다. refresh는 캐시를 매번 최신으로 채우므로 학습 기준일 이후 행이 모두 `RETROSPECTIVE_INFERENCE`로 나옵니다. 둘 다 동결 모델의 학습 기준일 이후 추론이며 진단 보고서는 함께 묶어 다룹니다.
- **API 키**는 V1 `.env`(`KRX_API_KEY`, `ECOS_API_KEY`)에서 자식 프로세스 환경으로만 넘깁니다. 출력·파일에 남기지 않습니다.
- **시장별로 따로 씁니다.** `korea_scores.csv`는 한국이 기대 거래일 기준 `CURRENT`일 때만, `us_scores.csv`는 미국 과거 재현이 통과하고(`CURRENT` 또는 `DELAYED`) 점수가 있을 때만 바꿉니다. 조건에 안 맞는 시장은 이전 파일을 그대로 둡니다. 한국이 `CURRENT`가 아니면 미국만 갱신해도 종료 코드 2로 끝납니다(한국 기대 거래일 21:30 KST 이후 KRX 공개 전이 흔한 경우).
- 한국은 `provenance.json`(기존 형식 + `refresh` 실행 기록), 미국은 `us_provenance.json`에 출처 커밋·export SHA-256·수집 실행 ID가 남습니다. 각 import는 같은 export의 시장별 상태 블록을 `data/input/operational/<시장>.json`에 함께 저장합니다.
- **미국 점수는 배포 저장소 `main` 9bedc79 이후 코드에서만 나옵니다.** 그 이전 파이프라인은 Yahoo의 SPY 조정가격 재계산(과거 `SPY_1D_Return` 최대 1.6e-6 차이) 때문에 1e-9 재현 대조에서 미국을 `BLOCKED`로 보류합니다. 9bedc79의 `anchor_us_history`는 V1 캐시 행을 그대로 두고 이후 관측만 붙이므로 통과합니다. 이 저장소는 그 기준을 바꾸지 않고, 고른 `--source-ref`의 파이프라인 결과를 그대로 씁니다. 미국이 `BLOCKED`인 ref로 돌리면 `us_scores.csv`는 바뀌지 않습니다.
- 미국은 FRED 신용 금리(DBAA/DGS10)가 SPY·VIX보다 며칠 늦게 공개되는 일이 많아 `DELAYED`가 흔합니다. 이때 점수는 마지막으로 모든 원천이 관측된 날까지만 있습니다.

### 두 배치의 게시 규칙

`refresh-diagnostics.yml`(4시간, GitHub 고정 export)과 `daily-refresh.yml`(일일, 파이프라인 직접 실행)은 같은 `data/input`을 씁니다.

- **과거로 되돌리지 않습니다.** `import_data`/`import_us`는 기존 CSV보다 마지막 점수일이 오래된 입력을 게시하지 않습니다(`older_than_published`). 마지막 점수일이 같은데 점수·기록 유형이 다르면 기존 것을 유지합니다(`same_date_different_scores`). 가격만 바뀐 갱신과 더 새로운 날짜는 그대로 게시됩니다. 건너뛰면 결과의 `publication`에 이유가 남습니다.
- **두 배치는 동시에 돌지 않습니다.** 같은 concurrency group(`korea-data-<ref>`)을 쓰고, 저장은 둘 다 `scripts/push_data_commit.sh`로 합니다.
- **4시간 배치도 화면 export를 같이 갱신합니다.** import 뒤 `export_frontend`와 시나리오 빌더를 실행해 CSV와 화면 자료가 어긋나지 않습니다.
- **시장별로 게시합니다.** `qsignals.refresh` 종료 코드: 0 모두 갱신, 3 일부 시장 지연(검증된 다른 시장은 게시), 2 새 자료 없음(게시 없음, 오류 아님), 1 검증 실패(BLOCKED, 아무것도 쓰지 않음). 일일 workflow는 0·3일 때만 저장하고, 1과 파이프라인 오류는 실패로 끝납니다.
- 커밋 메시지의 시장별 날짜는 `scripts/published_dates.py`가 `provenance.json`(한국)과 `us_provenance.json`(미국)에서 읽습니다.

## GitHub Actions 갱신 오류 해결

`Daily V1 score refresh`(`.github/workflows/daily-refresh.yml`)는 `main`에 있으며 평일 22:00(KST)에 예약 실행됩니다. `Refresh Korea event diagnostics`와는 별도 작업입니다.

`KRX_API_KEY is not set (V1 .env or environment)` 오류는 실행에 필요한 Secret이 전달되지 않았다는 뜻입니다. 실패 실행에서는 `KRX_API_KEY`와 `ECOS_API_KEY`가 모두 빈 값이었습니다.

1. 이 저장소의 [Settings → Secrets and variables → Actions](https://github.com/JM973279/market-portfolio-risk-signals-intelligence/settings/secrets/actions)에서 **Repository secrets**로 `KRX_API_KEY`와 `ECOS_API_KEY`를 추가하거나 값을 갱신합니다.
2. 두 값은 **Variables**가 아니라 **Secrets**에 저장해야 합니다. 다른 저장소의 Secrets와 로컬 `.env`는 GitHub runner로 자동 전달되지 않습니다. 이 작업에는 `environment:` 지정이 없으므로 Environment secrets만 등록해도 전달되지 않습니다.
3. 설정 후 실패 실행에서 **Re-run failed jobs**를 선택합니다. 재실행은 원래 실행의 커밋을 사용합니다. 수정된 workflow 자체를 확인하려면 `feat/live-score-refresh`를 선택해 새 수동 실행을 시작해야 합니다.
4. 키 누락 검사는 수집 전에 실행되어 누락된 **이름만** 오류와 작업 요약에 표시합니다. Secret 값은 출력하지 않습니다. 키가 존재해도 만료·권한·제공처 공개 지연은 별도 확인이 필요하며, 점수가 최신성 검사를 통과해야 발행됩니다.

Secrets 공식 안내: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
재실행 공식 안내: https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs

## 웹 화면 (`frontend/`)

배포 저장소의 `frontend/`를 9bedc79에서 그대로 복사했습니다(커밋 216198a, 트리 해시 동일). 그 위에 이 저장소 작업만 얹었습니다: 사례 분석 시나리오 라이브러리(`korea-scenario-library.patch`), 현재 점수가 없을 때 시장 카드에 마지막 유효 점수 표시, 데이터 점검 스크립트를 특정 실행 수치 대신 규칙으로 검사. 배포 저장소는 바꾸지 않습니다.

```bash
python3 -m qsignals.refresh                        # 점수 CSV + data/input/operational/{korea,us}.json
python3 -m qsignals.export_frontend                # → frontend/public/data/operational-markets.json
python3 -m market_engine.scenarios.build_korea_library   # → frontend/public/data/korea-scenarios.json
cd frontend && npm ci && npm run build && npm run start   # http://localhost:3000
```

- **이 저장소 데이터로 바뀌는 것:** `operational-markets.json`(시장 카드, 미국·한국 시장 페이지의 운영 추론, 헤더 날짜)과 그것을 읽는 `korea-scenarios.json`. `export_frontend`는 `data/input/operational/<시장>.json`(점수 CSV와 같은 export에서 import가 저장한 시장별 상태 블록, 가격 없음)을 합치고, 모든 점수가 `<시장>_scores.csv`와 같은지 확인한 뒤 씁니다. 두 시장은 서로 다른 수집 실행에서 올 수 있고 `runId`에 둘 다 적힙니다.
- **복사본 그대로인 것:** `global-markets.json`(walk-forward OOS 연구 export), `korea-monitor.json`(시장 확산도·과거 검증). 동결 연구 자료라 갱신하지 않습니다.
- **배포 화면과 다른 점(refresh로 갱신한 경우):** refresh가 한국 원천 이력을 매번 최신으로 채우므로 학습 기준일 이후 한국 행은 모두 `RETROSPECTIVE_INFERENCE`(과거 캐시 재현 추론)로 표시됩니다. 배포 사이트는 V1 캐시 끝(10/15) 이후를 `OPERATIONAL`로 표시합니다. 점수 값은 같습니다.
- **KR/EN:** EN 토글이면 포트폴리오 iframe을 `/portfolio-lab?lang=en`으로 열고 API도 영어 문구로 받습니다. 자세한 규칙은 위의 [화면 언어](#화면-언어-kr--en) 절을 보세요.
- **포트폴리오 분석 메뉴**는 이 저장소의 포트폴리오 분석(`python3 -m qsignals.portfolio_server`, 기본 3108)을 사이트 안에 iframe으로 보여 줍니다. 사이트가 `/portfolio-lab`, `/portfolio/{app.js,style.css}`, `/api/portfolio/*`를 그 서버로 넘깁니다. 주소가 다르면 빌드할 때 `PORTFOLIO_API_INTERNAL_URL`로 지정합니다. 서버는 같은 출처만 iframe을 허용하고(`frame-ancestors 'self'`), 같은 PC의 프록시가 보낸 `X-Forwarded-Host`만 출처로 인정합니다.

## 구조

```text
data/events/kospi_2026_events.csv   급락일 주석 (사람이 작성)
data/events/scheduled_us_2026.csv   예정 미국 발표 (공식 출처·확인일)
data/events/preopen_log.csv         개장 전 뉴스 기록 (실시간 누적)
data/input/overnight_*              EWY·SOX 종가와 provenance (overnight workflow가 생성)
data/input/korea_scores.csv         V1 점수·MSI·KOSPI200 (import_scores가 생성)
data/input/provenance.json          출처 커밋·sha256·가격/점수 종료일·누락 거래일
data/input/kospi200_naver.xml        가격 제공처 원응답 (재현용)
data/calendar/                     KRX 거래일 달력·추가 휴장 출처
data/input/us_scores.csv            미국 V1 점수·MSI·SPY (비교용, 진단에는 쓰지 않음)
data/input/us_provenance.json       미국 출처 커밋·sha256·행 수, 수집 상태
qsignals/refresh.py                 동결 파이프라인을 임시 사본에서 실행해 최신 점수 수집
qsignals/view.py                    reports/dashboard.html 생성 (data/input·reports만 읽음)
qsignals/export_frontend.py         frontend/public/data/operational-markets.json 생성·검증
data/input/operational/             시장별 상태 블록 (CSV와 같은 export에서 import가 저장)
frontend/                           배포 저장소 화면 복사본 + 이 저장소 수정
infra/aws/                          전체 사이트 Docker compose·Lightsail 배포 스크립트
qsignals/portfolio*.py              포트폴리오 성과·요인분해·위험·역사적 재현 계산과 웹/API 서버
qsignals/portfolio_i18n.py          포트폴리오 API의 영어 문구 (?lang=en)
qsignals/portfolio_web/             포트폴리오 분석 화면 (사이트 iframe·단독 실행 공용)
data/portfolio/                     GitHub Actions가 검증해 저장한 포트폴리오 가격·팩터 스냅샷
market_engine/scenarios/            한국 급락 시나리오 큐레이션·빌더 (사례 분석 화면)
scripts/setup_inference_env.sh      refresh용 별도 Python 환경
qsignals/scores.py                  점수 시계열 병합·검증
qsignals/events.py                  이벤트 스키마·검증
qsignals/diagnostics.py             사전 경보 판정, 대형 하락일 스캔
qsignals/report.py                  CSV / 한국어 Markdown 출력
qsignals/overnight*.py              개장 전 미국 가격 수집(Actions 전용)·정렬·overlay 실험
qsignals/msi_check.py               공식 MSI 급락 인정 진단
qsignals/preopen.py                 개장 전 뉴스 기록 검증·평가 조건
qsignals/schedule.py                예정 미국 발표 → KRX 반영 거래일
qsignals/stats.py                   로지스틱·PR-AUC·블록 부트스트랩 (표준 라이브러리)
qsignals/signal_checks.py           신호 보강 점검 보고서
reports/                            진단 결과
```

점수 병합: walk-forward OOS(`global-markets.json`, ~2026-09-16)가 우선이고, 그 이후 날짜는 동결 모델(학습 기준일 2026-09-16)의 사후·운영 추론(`operational-markets.json`)으로 채웁니다. 행마다 `record_type`으로 구분합니다. 미국도 같은 규칙이며 OOS는 2026-09-21까지입니다.

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
