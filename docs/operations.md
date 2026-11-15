# 운영 · Operations

M/PRI의 데이터는 GitHub Actions가 수집·검증해 이 저장소 `main`에 올리고, 웹과 API는 그 스냅샷만 읽습니다. 이 문서는 자동화 일정과 실패 처리 방식을 정리합니다. 시각은 한국 시간(KST)입니다.

*Data is collected and verified by GitHub Actions and committed to `main`; the web app and API read only those snapshots. Times are KST.*

## Workflows

| Workflow | 일정 · Schedule (KST) | 하는 일 · What it does |
| --- | --- | --- |
| [Daily V1 score refresh](../.github/workflows/daily-refresh.yml) | 화~토 09:07, 12:07 | 동결 V1 모델로 한국·미국 위험 점수 갱신, 화면용 자료 재생성 · V1 risk scores for both markets |
| [Refresh verified Korea portfolio data](../.github/workflows/refresh-korea-portfolio.yml) | 월~금 11:47, 14:47, 23:47 | 국내 주식·ETF 수정종가(Yahoo), VKOSPI(KRX), 국고채 금리(ECOS) · Korea portfolio data |
| [Validate and refresh portfolio analysis](../.github/workflows/refresh-portfolio.yml) | 4시간마다 :17 | 미국 ETF 가격, VIX, FRED 금리 · US portfolio data |
| [Refresh overnight US prices](../.github/workflows/refresh-overnight.yml) | 4시간마다 :47 | 한국 개장 전 참고용 EWY·SOX 가격 · US pre-open reference |
| [Refresh Korea event diagnostics](../.github/workflows/refresh-diagnostics.yml) | 4시간마다 :37 | 급락 사건 진단 보고서 · sell-off diagnostics |
| [Extend the KRX trading calendar](../.github/workflows/update-krx-calendar.yml) | 매월 1·15일 10:23 | 거래일 달력을 만료 90일 전에 다음 해 말까지 연장 · extends the trading calendar |
| [Restart dropped data schedules](../.github/workflows/watchdog.yml) | 매시 :29 | GitHub가 빠뜨린 예약 실행을 다시 시작 · restarts dropped scheduled runs |
| [Deploy verified main to Lightsail](../.github/workflows/deploy-lightsail.yml) | 데이터 갱신 후, 6시간마다 예비 | 이미지 빌드·검사 후 AWS Lightsail 배포 · build, check and deploy |
| [Publish Docker image](../.github/workflows/docker-publish.yml) | `main` 변경 시 | GHCR에 포트폴리오 서버 이미지 게시 · publishes the portfolio server image |

## 데이터 원칙 · Data rules

- **검증된 것만 게시합니다.** 모든 스냅샷은 원천 응답의 SHA-256, 수집 시각, 코드 커밋, Actions 실행 ID, 실제 관측일을 함께 기록합니다(`current.json`, `provenance.json`).
- **과거 값으로 채우지 않습니다.** 관측이 빠진 날은 비우거나 제외하고 그 사실을 기록합니다.
- **관측일이 뒤로 가지 않습니다.** 새 결과가 이미 게시된 날짜보다 오래되면 게시하지 않습니다.
- **한국과 미국은 따로 갱신합니다.** 한 시장의 원천이 늦거나 실패해도 다른 시장은 게시되고, 실패한 시장은 마지막 검증본을 유지합니다.

## 실패 처리 · Failure handling

| 상황 · Case | 처리 · Behaviour |
| --- | --- |
| 원천이 늦음 · provider late | 경고만 남기고 마지막 검증본 유지, 3거래일 넘게 밀리면 실패 · warning; fails only past 3 sessions behind |
| 원천 일시 장애 · transient outage | 재시도 후 다음 예약 실행에서 다시 시도 · retried on the next run |
| GitHub 예약 누락 · dropped schedule | watchdog이 45분 뒤 직접 실행 · restarted by the watchdog |
| 배포 전 검사 실패 · pre-deploy check fails | Lightsail에 올리지 않음 · not deployed |
| 배포 후 검사 실패 · post-deploy check fails | 이전 배포로 되돌림 · rolled back |

## 배포 · Deployment

이미지를 runner에서 띄워 [`scripts/check_site.py`](../scripts/check_site.py)로 모든 화면 응답, 점수 파일 일치, 한국·미국 포트폴리오 가격일과 분석 결과를 확인한 뒤 배포합니다. AWS 권한은 GitHub OIDC로 받는 1시간짜리 자격증명이며, 저장된 AWS 키는 없습니다. 수동 배포는 [`infra/aws/deploy_lightsail.sh`](../infra/aws/deploy_lightsail.sh)를 씁니다.

*Images are started on the runner and checked with `scripts/check_site.py` before deploying. AWS access uses short-lived GitHub OIDC credentials; no AWS keys are stored.*

## 필요한 설정 · Required settings

- Repository secrets: `KRX_API_KEY`, `ECOS_API_KEY`
- Repository variables: `AWS_DEPLOY_ROLE_ARN`, `LIGHTSAIL_AUTODEPLOY=true` (선택 · optional: `KRX_API_KEY_EXPIRES`)
