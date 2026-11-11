# 포트폴리오 성과·벤치마크 요인분해

이 저장소에 추가한 독립 Python 웹/API 모듈입니다. 기존 한국 이벤트 진단과 점수 수집 규칙은 유지합니다. 다른 AWS 저장소를 수정하거나 배포하지 않습니다.

## 실행

Python 3.10+ 표준 라이브러리만 필요합니다.

```bash
python3 -m qsignals.portfolio_server
# http://127.0.0.1:3108/portfolio
```

처음부터 GitHub에서 검증 파일을 다시 받아 재현하려면 다음을 실행합니다. 웹/API 요청에서는 외부 제공처를 호출하지 않습니다.

```bash
# 운영 갱신은 아래 Actions가 수행합니다. 명시적 수동 재현 시에만 수집 의존성을 설치합니다.
python3 -m venv /tmp/portfolio-collector
/tmp/portfolio-collector/bin/pip install -r requirements.portfolio-refresh.txt
/tmp/portfolio-collector/bin/python -m qsignals.portfolio_refresh
# 동결 원본만 다시 확인하는 수동 옵션(운영 갱신 경로가 아님)
python3 -m qsignals.portfolio_import --source-ref COMMIT_SHA
python3 -m unittest discover -s tests -t .
```

기본 원본은 기존 데이터 연결과 같은 `tina77302/market-portfolio-risk-intelligence`, ref `main`입니다. 조회 시 SHA 하나로 고정하고 그 커밋의 `data/portfolio/{prices.csv,factors.csv,universe.csv,snapshot_meta.json,scenarios.json}`만 읽습니다. 실패하면 기존 `current.json`은 보존하며, 내용이 동일하면 코드 커밋만 바뀌어도 기존 가격 버전·수집시각을 보존해 불필요한 데이터 커밋을 만들지 않습니다. 과거 버전은 `snapshots/<가격 버전 ID>/`에 보존합니다. 기본 원본 SHA는 `source_commit`에, 새 수집본의 내용 해시는 `snapshot_id`에 따로 기록합니다. 제공처 정규화 응답·FRED 원응답·거래일 달력도 해시와 함께 보관합니다.

최초 원본 스냅샷은 2026-10-23에서 멈춰 있었습니다. 현재 Actions는 같은 GitHub 원본 저장소·main·입력 경로에서 자산 목록과 동결 기준을 읽은 뒤, Yahoo 전체 수정종가 이력과 VIX·FRED DGS10을 직접 수집·검증해 이 저장소에 별도 운영 버전으로 저장합니다. 웹/API는 계속 `data/portfolio/current.json`과 그 파일이 지정한 GitHub 검증 파일만 읽습니다.

실제 최신 가격일은 `price_as_of`, 금리 자료까지 있는 위험 추정일은 `collection.risk_as_of`로 구분합니다. 금리 결측을 채우지 않으며 3거래일 넘게 지연되면 발행을 보류합니다. XNYS 휴장·조기 폐장을 반영해 장 마감 2시간 뒤의 완료된 세션까지만 수집합니다. 지원 자산 하나라도 그 구간에서 관측이 누락되면 기존 검증본을 보존합니다.

과거 수정종가의 재수정이 있으므로 전체 이력을 같은 수집본으로 교체하고 과거/신규 가격을 이어 붙이지 않습니다. 원본 연구 스냅샷은 보존하며 차이 감사표를 기록합니다. 원본 기준 저장소·ref·수신 경로를 다른 저장소로 바꾸지 않았습니다. 웹/API에서 외부 가격을 수집하거나 로컬 다른 프로젝트를 기본 입력으로 사용하지 않습니다.

[Validate and refresh portfolio analysis](../.github/workflows/refresh-portfolio.yml)는 4시간마다 고정한 GitHub 기준과 전체 제공처 시계열을 수집·검증한 뒤 데이터만 커밋합니다. `workflow_dispatch`도 지원합니다. GitHub Actions 자체의 실행 허용 및 저장소 규칙을 따릅니다.

## 화면 흐름

1. **분석 조건**: 지원 종목 최대 10개, 비중 합계 100%, 시작 투자금액, 기간, 벤치마크.
2. **과거 가상성과**: 기간 수익률, 가상 손익·종료금액, 벤치마크 대비 초과수익, 최대 낙폭. 누적 수익률 차트와 날짜 선택기.
3. **수익 기여도**: 종목 수익률, 시작 비중, 수익률 기여(%p), 손익 기여(USD). 막대는 이익·손실을 양쪽으로 표시.
4. **성과요인**: 자산배분, 자산군 내 선택, 상호작용을 초과수익으로 대사. 자산군/주식 내 섹터별 전환.
5. **위험 분석**: 별도 고정 기간의 연율 변동성, 위험 기여도, 상관관계, 개별 팩터 베타, 역사적 충격의 가상 손익.
6. **비중 비교**: 같은 날짜·금액·가격 버전·벤치마크로 두 비중을 비교. 누적 수익률 3개 선과 성과·요인·위험 변화.

입력 변경 후 기존 결과는 흐리게 표시하고 재분석을 요구합니다. 늦게 도착한 과거 요청이 새 입력 결과를 덮지 않도록 요청 버전을 확인합니다. 가격이 없는 날짜를 이월하거나, 실패한 결과를 0으로 대체하지 않습니다.

## 비교 기준

- **SPY**: 수정종가로 비교하는 미국 대형주 ETF.
- **주식·국채 60:40**: 시작일 SPY 60%, IEF 40% 후 보유. 월별 리밸런싱 지수와 구별합니다. 제품의 비교용 예시이며 추천 비중을 뜻하지 않습니다.
- **사용자 지정**: 지원 자산과 시작 비중을 사용한 동일 방식의 기준 포트폴리오.

분석이 끝난 뒤 성과가 유리해 보이는 비교 기준으로 자동 변경하지 않습니다. 주식 100% 포트폴리오와 SPY를 자산군별로 비교하면 양쪽 모두 주식 100%이므로 자산배분 효과는 0입니다. 주식 안의 차이를 섹터배분 효과로 보려면 별도 과거 섹터 자료가 필요합니다.

## 계산 규약

수익률은 API에서 소수 단위입니다. 비중 입력은 % 단위이며 합계 100%의 반올림 오차 0.01%p를 허용하고 실제 적용 비중을 정규화합니다. 화면에는 수익률 %, 수익 기여/초과수익 %p를 구분합니다.

```text
V(t) = 시작금액 × Σ [시작 비중_i × 수정종가_i(t) / 수정종가_i(시작일)]
종목 수익 기여 = 시작 비중_i × (종목 종료가격 / 시작가격 − 1)
최대 낙폭 = min_t [V(t) / 과거 최대 V − 1]
초과수익 = 포트폴리오 기간 수익률 − 벤치마크 기간 수익률
```

시작 비중으로 매수 후 보유하며 기간 중 리밸런싱·입출금은 없습니다. 따라서 일정 비중 일간 수익률을 계속 복리로 누적하는 방식과 다릅니다. 배당·분할 수정종가를 사용하므로 배당을 따로 다시 더하지 않습니다. 세금·수수료·환율은 미반영, USD 기준입니다. 현재 선택 자산을 과거에 보유했다고 가정하며 실제 계좌 성과나 미래 예측은 아닙니다.

단일 전체 기간 산술 Brinson–Fachler 3효과:

```text
배분_g = (내 그룹 비중 − 기준 그룹 비중) × (기준 그룹 수익률 − 기준 전체 수익률)
선택_g = 기준 그룹 비중 × (내 그룹 수익률 − 기준 그룹 수익률)
상호작용_g = 비중 차이 × 그룹 수익률 차이
Σ(배분 + 선택 + 상호작용) = 초과수익
```

미보유 그룹은 해당 기준 수익률로 두어 선택·상호작용은 0, 미보유 효과는 배분으로 설명합니다. 벤치마크 밖 자산군은 미리 선언한 참조 SPY(주식), IEF(채권), GLD(원자재)의 같은 기간 수익률을 사용하고 화면에 표시합니다. 참조 자료가 없으면 해당 요인분해만 보류합니다. 월별 효과를 단순 합산해 연간 효과로 표시하지 않습니다. 대사 오차 허용치는 원정밀도 수익률 1e-10이며 실패하면 그 요인 결과를 발행하지 않습니다.

위험 추정은 원본 `window_start~window_end`를 유지합니다. 변동성·상관·위험 기여는 일정 비중 일간 수익률 기준입니다. 팩터는 각각 독립 단순회귀이고 금리 변화는 bp, VIX 변화는 pt입니다. 금리 결측을 이월하지 않습니다. 시나리오는 베타 × 고정 10거래일 충격의 선형 근사이며 손익을 합산하거나 미래 손실확률로 해석하지 않습니다. 스트레스 기준금액은 시작 투자금액입니다.

## 실제 섹터 분석의 데이터 연결

기본 배포 자료에는 과거 SPY 섹터 구성·수익률과 시점별 분류가 없으므로 **자료 연결 필요**로 표시합니다. 계산 엔진과 연결 경로는 구현되어 있으며 단위 검사에서 합계를 확인합니다. 예시 숫자를 실제 SPY 결과로 게시하지 않습니다.

검증된 자료를 GitHub 수집 단계에서 `data/portfolio/sector-inputs.json`과 원응답 파일로 함께 저장합니다. 웹은 이 저장 파일만 읽습니다. 인덱스 형식:

```json
{
  "schema_version": 1,
  "records": [{
    "period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
    "price_snapshot_sha": "원본 포트폴리오 가격 커밋 40자",
    "benchmark_weights": {"SPY": 1.0},
    "currency": "USD",
    "return_basis": "dividend_split_adjusted_close",
    "classification_policy": "fixed_start_point_in_time",
    "classification_as_of": "시작일과 같은 YYYY-MM-DD",
    "classifications": {"AAPL": "Information Technology"},
    "benchmark_groups": {
      "Information Technology": {"weight": 0.0, "return": 0.0}
    },
    "off_benchmark_returns": {},
    "sources": [{"path": "sector_sources/receipt.json", "url": "https://원천주소", "sha256": "원응답 SHA-256"}]
  }]
}
```

위 예시는 형식 설명이며 실제 데이터가 아닙니다. 모든 관련 주식 분류·전체 기준 그룹과 실제 비중·수익률을 채워야 합니다. 시작일 기준 분류, 동일 실제 거래일 구간, 가격 커밋 및 벤치마크 비중이 정확히 일치해야 합니다. 각 원응답 해시를 검증합니다. 섹터 합산 수익률이 같은 주식 벤치마크 가격 수익률과 일치하지 않으면 보류합니다. 자료 출처와 사용권, 경제적 의미의 검증은 수집·검토 단계에서 수행해야 하며 해시 일치만으로 원천 내용의 정확성이 증명되지는 않습니다.

주식 구간은 포트폴리오/벤치마크 각각 100%로 정규화해 분석하며 전체 자산군 효과에 다시 더하지 않습니다. 현재 연결 경로는 직접 주식만 지원합니다. ETF가 포함되면 과거 look-through와 수익률 재구성 자료가 필요하다는 상태를 표시합니다. 현재 ETF 보유비중을 과거로 복사하지 않습니다. 분류가 바뀐 기간은 시작일 분류 고정 정책으로 만든 그룹 수익률과 맞아야 합니다.

## API

```text
GET  /health                    검증 자료 읽기 및 실제 가격 종료일
GET  /api/portfolio/meta         지원 자산·기준·가능 기간·출처
POST /api/portfolio/analyze      성과·요인·별도 위험
POST /api/portfolio/compare      동일 조건의 두 비중 비교
```

분석 요청:

```json
{
  "holdings": [{"ticker": "SPY", "weight": 100}],
  "initial_value_usd": 100000,
  "start": "2025-10-23",
  "end": "2026-10-23",
  "benchmark": {"kind": "spy"}
}
```

사용자 지정 기준은 `{"kind":"custom","holdings":[...]}`이며 비교 요청은 같은 객체에 `proposed_holdings`를 추가합니다. 가격 기간 밖 요청·중간 누락 가격·중복 종목·비정상 숫자·합계 오류는 422, 읽기 불가능하거나 해시가 틀린 필수 자료는 503입니다. 성과 자료가 유효하면 위험 또는 선택적 섹터 입력 실패가 전체 성과를 숨기지 않습니다. 포트폴리오 입력은 서버에 저장하지 않습니다.

로컬 서버는 기본 loopback 바인딩이며 같은 출처의 JSON 요청만 받습니다. 외부 배포가 필요하면 TLS·인증·리버스 프록시 등 별도 운영 구성을 검토합니다. 이 변경은 AWS 배포를 수행하지 않습니다.

## 검증

Python 단위 검사는 매수 후 보유와 매일 리밸런싱의 차이, 종목 기여 합계, 낙폭, 동일 기준의 0 초과수익, BF 3효과 대사, 0 비중·기준 밖 그룹, 섹터 입력·기간·자료 버전·해시 오류, 실패 시 이전 검증본 보존, 원본 커밋 고정, 기존 이벤트 진단을 포함합니다.

개발용 Playwright가 설치된 환경에서는 실제 서버를 실행한 뒤:

```bash
PLAYWRIGHT_MODULE=/path/to/playwright node scripts/check_portfolio_browser.cjs
```

런타임 설치 의존성은 없습니다. 브라우저 검사는 실제 계산 API·커스텀 벤치마크·비중 비교 차트·단위 전환·키보드 날짜 선택·섹터 미연결 상태·입력 거부·360px 화면을 확인합니다. 선택적 `PORTFOLIO_QA_FONT`는 한글 글꼴이 없는 개발 환경의 스크린샷에만 사용합니다.

참고: [PortfolioAttribution 공식 계산 문서](https://github.com/braverock/PortfolioAttribution/blob/master/man/Attribution.Rd), [CFA Society Netherlands 방법론](https://cfasociety.nl/en/publications/setting-up-a-performance-attribution-framework/be2d24cc-f833-11ea-8a1e-005056b303d3).

## 최신 수집본 재현

```bash
/tmp/portfolio-collector/bin/python -m qsignals.portfolio_refresh --replay data/portfolio/current.json --output-dir /tmp/portfolio-replay
```

이 옵션은 기록된 GitHub 원본 SHA를 다시 읽고, 가격·금리 제공처 호출 대신 보존된 응답을 해시 검증해 재사용합니다. 제공처 재현이며 GitHub 원본 조회는 남아 있습니다. 원본의 역사적 충격 정의는 다시 추정하지 않고 `scenario_as_of`를 별도로 표시합니다. 위험 베타·변동성 추정 기간은 새로 확보한 자료로 이동합니다. 새 수집본이 기존 가격 기준일보다 과거이면 게시하지 않습니다.
