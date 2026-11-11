# Global dashboard redesign · 2026-10-29

## Architecture

The root server layout reads the two versioned local exports with `use cache`.
A persistent client shell provides Korean/English copy, sidebar navigation and
shared data. The home route and seven validated named routes render compact,
reusable analytical panels. Mobile navigation collapses into an accessible menu.
No third-project API exists to connect; the original V1 project's historical,
validation, latest and data-health endpoints were inspected but are not consumed.
This dashboard uses explicit, read-only file snapshots instead.

## Created files

- `src/components/dashboard-shell.tsx`: shared context, persistent sidebar and language toggle.
- `src/components/dashboard-view.tsx`: eight page compositions, Korea date controls and US historical evidence.
- `src/components/research-panels.tsx`: market cards, breadth bars, stored correlation matrix, validation, timeline, states and sources.
- `src/components/market-chart.tsx`: interactive calendar-aligned price/OOS chart with missingness and keyboard inspection.
- `src/components/country-flag.tsx`: platform-independent SVG flags.
- `src/lib/dashboard-copy.ts`: expanded bilingual dictionary.
- `src/lib/dashboard-data.ts`: cached export loading and unavailable handling.
- `src/lib/dashboard-types.ts`: presentation data contracts.
- `src/lib/chart-data.ts`: calendar range and gap-aware path helpers.
- `src/app/[view]/page.tsx`: seven named routes, static parameters and unknown-route rejection.
- `scripts/prepare-dashboard-data.py`: manual, read-only original-V1/Korea presentation bridge.
- `scripts/check-chart-data.mjs`: date and missing-path verification.
- `public/data/global-markets.json`: new traceable presentation snapshot.
- `public/images/seoul-header.webp`: decorative generated header (~182 KB).
- `public/fonts/PretendardVariable.woff2`, `public/fonts/OFL.txt`: local Korean/English typography and license.
- `docs/ASSETS.md`: asset source and full image prompt.
- `../tests/test_dashboard_snapshot.py`: six source-integrity and missing-source checks.

Modified files: `src/app/layout.tsx`, `src/app/page.tsx`,
`src/app/globals.css`, `package.json` (chart check script), `README.md`.
The pre-existing monitor component and dictionary remain available; research
scripts, models, validation documents and the original Korea export are unchanged.
Pre-existing unrelated working-tree changes were preserved.

## Verified source coverage

| Scope | File | Last observation / role |
| --- | --- | --- |
| Original, separate V1 US | `market-stress-early-warning/data/processed/oos_predictions_10d.csv` | 2026-09-21; 5,060 stored 10D OOS rows |
| Original, separate V1 US | `market-stress-early-warning/data/features/feature_matrix.csv` | 2026-10-05; SPY, MSI, official threshold, stored stress flag |
| Original, separate V1 US | `market-stress-early-warning/data/processed/multi_horizon_metrics.csv` | Stored XGBoost 1D/5D/10D/20D metrics; checked against matching OOS counts and periods |
| Current project Korea | `data/processed/early_warning_v2/korea_oos_predictions_v1_reproduction_10d.csv` | 2026-09-16; frozen reproduction OOS |
| Current project Korea | `data/processed/early_warning_v2/korea_feature_matrix_v1_reproduction.csv` | 2026-10-02; KOSPI200, official MSI/threshold |
| Current project Korea | `data/processed/signal_divergence/korea_breadth_features.csv` | 2026-10-27; six stored shares and past-only percentile ranks |
| Current project Korea confirmation | `data/processed/signal_divergence/cross_asset_signal.csv` | 2026-10-02; stored 20-observation pairwise correlations and severity percentiles |
| Current project Korea interpretation | `market_engine/signal_divergence/VALIDATION.md`, `market_engine/early_warning_v2/EXPERIMENTS.md` | Preserved episode validation and separately labeled rounded October reports |

The presentation snapshot contains 5,070 US date rows and 2,479 Korea date rows.
There are no forward-filled model observations. Source paths, row counts and
SHA-256 fingerprints are visible on `/sources` and retained in the snapshot.
Original V1 model artifacts were inspected as separate historical project context;
no model was loaded or used for new inference. V2-A remains experimental and is
not deployed by this frontend.

## Connected charts and interpretation

- US history: actual SPY prices in USD/share, original 10D OOS scores in percent,
  and stored MSI in the inspection readout. SPY is not relabeled as S&P 500 points.
- Korea history: stored KOSPI200 points, frozen V1 reproduction OOS scores and MSI,
  joined strictly on exact dates already in the monitor history.
- Breadth bars/trend: existing stock shares, past-only percentiles, extreme counts
  and 2-of-3 persistence. The selected empirical CDF `>=0.90` convention is intact.
- Correlation matrix: stored KOSPI200/SPY/TLT/GLD pairs on its labeled historical
  date; not current, not a US rule and not an invented 3-month matrix.
- October timeline/table: reported V1/returns versus independently stored breadth
  and computed persistence. The October 12 selloff was not predicted. October
  13 activation is a reported retrospective finding; absent October official MSI
  and post-OOS V1 observations prevent full independent divergence reproduction.

## Remaining availability and limitations

Current V1/MSI observations at the October 27 snapshot are missing for both
markets. The Korean final state stays UNKNOWN; September 16's complete state is
not carried forward. US original-V1 OOS ends September 21. No live inference,
scheduler, live API, exchange-calendar freshness guarantee or synchronized
cross-market risk estimate is implemented. No validated US breadth detector,
US-specific divergence rule or US correlation detector has been supplied.

Korea historical survivorship bias and inherited US-holiday price carrying in
correlation research remain disclosed. US metrics are stored classification
results, whereas Korea's 18/6/33.3%/6-day/~4.2-per-year figures are separate
reported episode research. Neither is represented as current accuracy. Source
identifiers and unrecognized source diagnostics retain their original language.
The Seoul hero is an AI-generated decorative illustration, not a current photo.

## Verification

- Existing research regression tests: 10 passed.
- Presentation snapshot checks: 6 passed, including exact values, hashes,
  unavailable original project, invalid dates/units and preserved saved metrics.
- Chart helper checks: calendar months/leap years, exact time spacing, null path
  breaks and all-missing handling passed.
- Standalone TypeScript, ESLint and optimized production build passed.
- Browser checks and final fingerprint verification are recorded below after the
  final production-preview pass. No commit, push, deployment or retraining.

Final production browser pass (Chromium): all eight routes passed at desktop
1536×1150 and mobile 390×844, plus the tablet dashboard at 1024×900. KR/EN,
route persistence, chart range/keyboard inspection, latest/last-complete date
controls, the mobile menu and horizontal overflow checks passed. Browser console
and resource errors: **zero**. Desktop, mobile and tablet screenshots were visually
reviewed, including bundled Korean glyphs and flags. Tablet analytics stack for
readability. Temporary browser runtime libraries were extracted under `/tmp`;
no system packages or frontend dependencies were installed for browser QA.

Final SHA-256 comparison: **162 existing research/export/model files unchanged**.
The original Korea JSON, research scripts, thresholds and validation artifacts
were preserved. Browser test servers were temporary; the pre-existing development
server was left untouched.
