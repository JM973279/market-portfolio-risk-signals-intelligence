# M/PRI · Korea & US Market Stress Monitor

A Korean-first, bilingual research dashboard built with the existing Next.js
16 / React 19 stack. This frontend does not run inference or collect live data.

```bash
npm run dev
npm run build
npm start
```

## MVP demo

For the existing Portfolio API startup, frozen snapshots, environment setup and demo steps,
see [MVP demo guide](../docs/MVP_DEMO_KO.md). No live collection or model training is needed for the demo.

## Routes

| Route | Content |
| --- | --- |
| `/` | Two-country overview, price/risk charts, Korea breadth/correlations, original US V1 performance, October timeline |
| `/portfolio` | Existing Portfolio API, Hidden Risk Map, Stress Test and What-if |
| `/us` | Separate original-V1 US history, stored metrics and observed stress rows |
| `/korea` | Frozen V1, official MSI, historical selector, exact exported monitoring state, breadth, confirmation, validation and holdout |
| `/breadth` | Korea diagnostics, stored correlation-date selector and breadth trend; US explicitly unavailable |
| `/validation` | Original US V1 classification metrics and separate experimental Korea episode validation |
| `/cases` | October 2026 retrospective timeline and reported/stored evidence table |
| `/sources` | Input periods, counts, paths, fingerprints and export downloads |
| `/methodology` | Signal roles, frozen breadth rule, ordered state classification and limitations |

The sidebar persists between routes. KR/EN uses the shared root context; Korean
is the initial language. The preference persists for the current browser tab, including page reloads.
The document language changes with the toggle. `dashboard-copy.ts` extends the
existing `monitor-copy.ts` dictionary. Source identifiers/diagnostics retain
their original language. Pretendard is bundled locally under its OFL license.

## Data

The original `public/data/korea-monitor.json` is unchanged. The new presentation
snapshot `public/data/global-markets.json` contains only explicitly read stored
columns from this repository and the separate original V1 project. No API is
required at runtime, and the original project's API is not connected here.

Manually prepare the optional presentation snapshot from the repository root:

```bash
python3 frontend/scripts/prepare-dashboard-data.py
# Optional: --original-v1-root /path/to/market-stress-early-warning
```

This writes only the new `global-markets.json`; it never writes research inputs,
loads model artifacts, computes new performance metrics, or trains a model. It
checks date uniqueness/order, numeric units, US OOS/feature agreement and stored
validation counts/periods. Missing original-V1 sources produce an unavailable US
snapshot. Rebuild/restart after refreshing either export.

Country overview metrics refer to the research snapshot date; historical V1/MSI
values are never carried into that date. Individual source dates and last
complete dates are shown separately. US and Korea observations are not combined
into a current global risk estimate.

Chart ranges use UTC calendar dates. Risk uses a fixed 0–100% right axis; SPY USD
or KOSPI200 points use the left axis. Nulls break paths; the region after the last
available OOS score is shaded. Hover and the keyboard observation slider expose
exact stored values. Correlation heatmaps use stored pairwise observations from
the Korea confirmation research, not a newly estimated three-month matrix or a
US detector. Diagonal cells are omitted.

## Validation

```bash
npm run test:charts
npm run test:integration
npx tsc --noEmit
npm run lint
npm run build
# Repository root:
.venv/bin/python -m unittest discover -s tests -v
```

See [implementation, data coverage and verification](docs/REDESIGN.md) and
[asset provenance, license and generation prompt](docs/ASSETS.md).

## 최신 데이터 N/A 진단

현재 원천별 종료일, 과거 정상 표시 예시, OOS와 운영 추론의 구분 및 갱신 작업의
우선순위는 [한국어 데이터 가용성 보고서](docs/DATA_AVAILABILITY_KO.md)를 참조하세요.
보고서 작성 과정에서 수집·추론·재학습이나 데이터 덮어쓰기는 수행하지 않았습니다.

배포 시 브라우저는 `/api/portfolio`를 같은 출처로 호출합니다. Next.js가 `PORTFOLIO_API_INTERNAL_URL` 또는 `PORTFOLIO_API_INTERNAL_HOSTPORT`로 프록시합니다(빌드 시 설정). 기본 로컬 API는 127.0.0.1:8000입니다. `NEXT_PUBLIC_PORTFOLIO_API_URL`은 직접 호출이 필요한 경우에만 설정하세요. 배포 및 롤백: [한국어 가이드](../docs/DEPLOYMENT_KO.md).
