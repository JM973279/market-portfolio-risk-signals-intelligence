"""Pre-registered signal checks → reports/signal_checks.md

    python3 -m qsignals.signal_checks

1. Overnight US prices (EWY, ^SOX) as an overlay on frozen V1  (experiment)
2. Official MSI recognition of large drops                     (diagnostic)
3. Pre-open news log status                                   (forward-only log)
4. Scheduled US releases near each sell-off and next sessions  (display only)

Nothing here changes the frozen Risk Score, MSI or thresholds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from qsignals import msi_check, overnight_eval, preopen
from qsignals.calendar import latest_closed_session, load_sessions
from qsignals.events import read_events
from qsignals.overnight import DEFAULT_CSV, DEFAULT_PROVENANCE, MAX_GAP_DAYS, align, read_overnight
from qsignals.schedule import EVENT_TYPES, nearby, read_schedule, upcoming
from qsignals.scores import read_scores

ROOT = Path(__file__).resolve().parent.parent
MODEL_LABELS = {"base": "V1 + 당일 KOSPI200", "overnight_EWY": "+ EWY", "overnight_full": "+ EWY + SOX"}
LABEL_NAMES = {"drop2": "다음 거래일 −2% 이하", "drop3": "다음 거래일 −3% 이하"}


def _pct(x, digits=1, signed=True):
    return "–" if x is None else (f"{x:+.{digits}f}%" if signed else f"{x:.{digits}f}%")


def _num(x, digits=3):
    return "–" if x is None else f"{x:.{digits}f}"


def _share(a, b):
    return "–" if not b else f"{a}/{b} ({a / b:.0%})"


def _model_name(name):
    return MODEL_LABELS.get(name, name)


def overnight_section(rows, events, csv_path, provenance_path, add):
    add("## 1. 개장 전 미국 가격 신호 (EWY·SOX) — 사전 등록 실험")
    add("")
    add("**질문:** 한국 장이 열리기 전에 이미 끝난 미국 장의 한국 ETF(EWY)·반도체 지수(SOX) 수익률을 동결 V1 점수에 더하면, 다음 거래일 KOSPI200 급락을 더 잘 가려내는가.")
    add("")
    add("**고정 규칙** (결과를 보기 전에 `qsignals/overnight_eval.py`에 기록):")
    add(f"- 판단 시점: KRX t일 종가 이후 ~ t+1일 개장 전. t+1일 직전에 끝난 미국 세션 수익률만 사용 (미국 날짜 < KRX 날짜, 간격 {MAX_GAP_DAYS}일 이내)")
    add(f"- 설계 구간: walk-forward OOS 점수가 있는 {overnight_eval.DESIGN_END}까지. 초기 학습 {overnight_eval.INITIAL_TRAIN}건, {overnight_eval.STEP}건마다 재학습, purge {overnight_eval.PURGE}")
    add("- 모델: ① V1 + 당일 KOSPI200 수익률 ② ①+EWY ③ ①+EWY+SOX (L2 로지스틱, 표준 라이브러리 구현)")
    add(f"- 평가: 평균정밀도(PR-AUC), 월 단위 블록 부트스트랩 {overnight_eval.BOOTSTRAP_REPS}회 (seed {overnight_eval.SEED})")
    add(f"- **판정:** {LABEL_NAMES[overnight_eval.PRIMARY_LABEL]} 라벨에서 ③의 개선폭 95% 구간이 전부 0보다 크면 '후보'")
    add(f"- {overnight_eval.HOLDOUT_START} 이후는 홀드아웃: 보고만 하고 어떤 선택에도 쓰지 않음")
    add("")
    over, meta = read_overnight(csv_path, provenance_path)
    if over is None:
        add("**상태: 데이터 미수집.** `Refresh overnight US prices` workflow가 처음 실행되면 `data/input/overnight_us.csv`가 생기고, 다음 진단 갱신 때 이 절이 채워집니다.")
        add("")
        return
    add(f"- 입력: {meta['provider']}, {', '.join(meta['tickers'])}, {meta['first_date']} ~ {meta['last_date']} ({meta['rows']:,}세션), sha256 `{meta['sha256'][:12]}…`")
    gaps = {t: len(v) for t, v in meta.get("missing_sessions", {}).items() if v}
    add("- 제공처 결측 세션: " + (", ".join(f"{t} {n}일" for t, n in gaps.items()) if gaps else "없음") + " (채우지 않고 표본에서 제외)")
    add("")
    result = overnight_eval.run(rows, over, meta, tickers=meta["tickers"])
    if result["status"] == "insufficient_design_samples":
        add(f"**상태: 설계 표본 부족** ({result['design_samples']}건). 판정하지 않습니다.")
        add("")
        return
    if result["status"] == "insufficient_positives":
        add("**상태: 설계 구간 급락 표본 부족.** 판정하지 않습니다.")
        add("")
        return
    verdict = "**후보 통과**" if result["status"] == "candidate" else "**근거 부족**"
    add(f"판정: {verdict} — 이 결과는 배포 저장소에서 17개 피처 ablation으로 다시 검증해야 하는 후보 여부일 뿐이며, 모델을 바꾸지 않습니다.")
    add("")
    for label, entry in result["labels"].items():
        if entry.get("status") == "insufficient_positives":
            add(f"### {LABEL_NAMES[label]}")
            add("")
            add("설계 구간 급락 표본이 부족해 평가하지 않습니다.")
            add("")
            continue
        add(f"### {LABEL_NAMES[label]} (OOS {entry['oos_range'][0]} ~ {entry['oos_range'][1]})")
        add("")
        add("| 모델 | 표본 | 급락 | PR-AUC | 상위 10% 포착률 | PR-AUC 개선 (95% 구간) |")
        add("|---|---:|---:|---:|---:|---|")
        for name, m in entry["oos"].items():
            g = entry["gain"].get(name)
            gain = "기준" if g is None else f"{g['ap_gain']:+.3f} ({_num(g['ci_low'])} ~ {_num(g['ci_high'])})"
            add(f"| {_model_name(name)} | {m['n']:,} | {m['positives']} | {_num(m['ap'])} | {_pct((m['recall_top10'] or 0) * 100, 0, False)} | {gain} |")
        if "holdout" in entry:
            h = entry["holdout"]
            add("")
            add(f"홀드아웃 {result['holdout_range'][0]} ~ {result['holdout_range'][1]} (설계 구간 전체로 학습한 모델을 그대로 적용):")
            add("")
            add("| 모델 | 표본 | 급락 | PR-AUC | 상위 10% 포착률 |")
            add("|---|---:|---:|---:|---:|")
            for name, m in h.items():
                add(f"| {_model_name(name)} | {m['n']:,} | {m['positives']} | {_num(m.get('ap'))} | {_pct((m.get('recall_top10') or 0) * 100, 0, False) if m.get('recall_top10') is not None else '–'} |")
        add("")
    tickers = result["tickers"]
    listed = [e for e in events if e.date in result["events"]]
    if listed:
        add("### 주석 급락일 직전 미국 세션 (홀드아웃)")
        add("")
        add("| 급락일 | " + " | ".join(f"직전 {t}" for t in tickers) + " | 급락일 KOSPI200 | 전날 V1 | 확률: 기준 | 확률: 미국 포함 |")
        add("|---|" + "---:|" * (len(tickers) + 4))
        for e in listed:
            x = result["events"][e.date]
            add(f"| {e.date} | " + " | ".join(_pct(x["overnight"][t], 2) for t in tickers)
                + f" | {_pct(x['next_ret'], 2)} | {x['v1'] * 100:.1f}% | {x['prob']['base'] * 100:.1f}% | {x['prob']['overnight_full'] * 100:.1f}% |")
        add("")
        add("- 전날 V1은 급락 전 거래일 종가 기준 점수입니다. 확률은 급락일 개장 전에 계산되는 '−2% 이하' 확률입니다 (기준 모델 vs 전일 미국 세션 포함 모델).")
        add("")
    recent = align(load_sessions(), over, meta)
    latest = sorted(recent)[-5:]
    if latest:
        add("### 최근 개장 전 신호")
        add("")
        add("| KRX 거래일 | 직전 미국 세션 | " + " | ".join(tickers) + " |")
        add("|---|---|" + "---:|" * len(tickers))
        for d in latest:
            o = recent[d]
            add(f"| {d} | {o.us_date} | " + " | ".join(_pct(None if o.returns[t] is None else o.returns[t] * 100, 2) for t in tickers) + " |")
        add("")


def msi_section(rows, add):
    r = msi_check.run(rows)
    d, h = r["design"], r["holdout"]
    add("## 2. 공식 MSI의 급락 인정 진단 — 사전 등록 진단")
    add("")
    add("**질문:** KOSPI200이 하루 크게 빠진 날, 공식 MSI가 그날을 스트레스로 인정했는가. 놓쳤다면 어떤 메커니즘 때문인가.")
    add("")
    add("**고정 규칙** (`qsignals/msi_check.py`):")
    add(f"- 급락: 연속 거래일 KOSPI200 하루 수익률 {msi_check.DROP_PCT:.0f}% 이하. 인정: 당일 MSI ≥ 공식 Stress 기준")
    add(f"- 랠리 상쇄: 놓친 날 중 급락 당일까지의 {msi_check.EQUITY_WINDOW}거래일 수익률이 여전히 양수인 경우 (MSI 주식 채널이 21일 수익률이라 직전 상승이 급락을 상쇄)")
    add(f"- 후보 보강 채널: {msi_check.PEAK_WINDOW}거래일 고점 대비 낙폭이 과거({msi_check.MIN_HISTORY}일 이상 누적) 하위 {msi_check.DRAWDOWN_PCT:.0%} 이내")
    add(f"- **판정:** 설계 구간({msi_check.DESIGN_END}까지)에서 공식 MSI가 급락의 {msi_check.MISS_SHARE_MIN:.0%} 이상을 놓치고, 보강 채널이 놓친 날의 {msi_check.RECOVER_SHARE_MIN:.0%} 이상을 잡으며, 전체 세션의 {msi_check.FLAG_RATE_MAX:.0%} 이하만 표시하면 'MSI 개정 제안 근거 있음'")
    add("")
    verdict = "**MSI 개정 제안 근거 있음**" if r["status"] == "revision_supported" else "**보강 채널 근거 부족** (공식 MSI가 놓치는 급락 자체는 아래 수치로 따로 확인)"
    add(f"판정: {verdict}")
    add("")
    add("| 구간 | 급락일 | MSI 놓침 | 그중 랠리 상쇄 | 놓친 날 중 보강 채널이 잡은 날 | 공식 MSI 스트레스 비율 | 보강 채널 표시 비율 |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for title, p in (("설계", d), ("홀드아웃", h)):
        name = f"{title} {p['range'][0]} ~ {p['range'][1]}" if p["range"] else title
        add(f"| {name} | {len(p['drops'])} | {_share(p['missed'], p['judged'])} | {p['rally_offset']} | {_share(p['recovered'], p['missed_with_drawdown'])} | "
            f"{_pct(None if p['official_flag_rate'] is None else p['official_flag_rate'] * 100, 1, False)} | {_pct(None if p['drawdown_flag_rate'] is None else p['drawdown_flag_rate'] * 100, 1, False)} |")
    add("")
    missed = [c for c in d["drops"] if c.official is False]
    if missed:
        add("설계 구간에서 MSI가 놓친 급락일:")
        add("")
        add(f"| 날짜 | KOSPI200 | {msi_check.EQUITY_WINDOW}거래일 수익률 | 1년 고점 대비 | 낙폭 백분위 | 보강 채널 |")
        add("|---|---:|---:|---:|---:|---|")
        for c in missed:
            flag = "–" if c.drawdown_flag is None else ("표시" if c.drawdown_flag else "미표시")
            add(f"| {c.date} | {_pct(c.ret_pct, 2)} | {_pct(c.ret21_pct)} | {_pct(c.drawdown_pct)} | {'–' if c.drawdown_rank is None else f'{c.drawdown_rank:.0%}'} | {flag} |")
        add("")
    add("연도별 공식 MSI 스트레스 판정 비율: " + ", ".join(f"{y} {v:.0%}" for y, v in r["official_rate_by_year"].items()))
    add("")
    add("- 보강 채널이 홀드아웃에서만 잘 맞는다면 그 결과로 채널을 고르면 안 됩니다. 판정은 설계 구간 기준입니다.")
    add("- 공식 MSI의 VKOSPI·신용 채널은 이 저장소에 없어 다시 계산하지 않습니다. 주식 채널 메커니즘만 진단합니다.")
    add("")


def preopen_section(rows, log_path, add):
    log = preopen.read_log(log_path)
    add("## 3. 개장 전 뉴스 기록 — 실시간 누적 전용")
    add("")
    add("**규칙** (`qsignals/preopen.py`):")
    add(f"- `data/events/preopen_log.csv`의 각 행은 직전 거래일 {preopen.CLOSE[0]}:{preopen.CLOSE[1]:02d} KST 이후, 해당 거래일 {preopen.OPEN_CUTOFF[0]:02d}:{preopen.OPEN_CUTOFF[1]:02d} KST 이전에 기록돼야 합니다. 과거를 나중에 채우는 행은 검증에서 거부됩니다.")
    add("- 분류자는 `manual`, `rule:<버전>`, `llm:<모델>`로 구분합니다. LLM은 과거 결과를 알 수 있으므로 실시간 기록만 인정합니다.")
    add(f"- 평가 조건: 분류자별 {preopen.MIN_LOGGED_SESSIONS}거래일 이상, 그중 {preopen.DROP_PCT:.0f}% 이하 하락 {preopen.MIN_DROP_SESSIONS}일 이상. 채택 기준은 위험 회피 표시가 연 {preopen.MAX_FLAGS_PER_YEAR}회 이하이면서 1절 모델 대비 개선이 확인될 것")
    add("")
    status = preopen.readiness(log, rows)
    if not status:
        add("**상태: 기록 없음.** 오늘부터 쌓는 기록만 평가 대상이 됩니다.")
    else:
        add("| 분류자 | 기록 | 결과 확인 | 하락일 | 상태 |")
        add("|---|---:|---:|---:|---|")
        for name, s in status.items():
            state = "평가 가능" if s["ready"] else f"평가 보류 ({s['with_outcome']}/{preopen.MIN_LOGGED_SESSIONS})"
            add(f"| `{name}` | {s['logged']} | {s['with_outcome']} | {s['drops']} | {state} |")
    add("")


def schedule_section(events, schedule_path, add, now=None):
    schedule = read_schedule(schedule_path)
    add("## 4. 예정된 미국 발표 — 표시 전용")
    add("")
    add("점수에는 넣지 않습니다. 2016~2025 파일럿에서 FOMC·CPI 직후 세션의 정확도 개선이 확인되지 않았습니다. 미국 발표는 한국 장 마감 뒤에 나오므로 **발표일 다음 KRX 거래일**에 붙여 표시합니다.")
    add("")
    now = now or datetime.now(timezone.utc)
    due = latest_closed_session(now)
    nxt = upcoming(schedule, due)
    add(f"### 다음 5거래일 ({due} 이후)")
    add("")
    if nxt:
        add("| 반영 KRX 거래일 | 미국 발표일 | 유형 | 내용 |")
        add("|---|---|---|---|")
        for s in nxt:
            add(f"| {s.krx_session} | {s.us_date} {s.release_time_et} ET | {EVENT_TYPES[s.event_type]} | [{s.description}]({s.source_url}) |")
    else:
        add("일정표에 등록된 발표가 없습니다.")
    add("")
    add("### 주석 급락일 근처 발표")
    add("")
    add("| 급락일 | 직전 2거래일~당일에 반영된 발표 |")
    add("|---|---|")
    for e in events:
        near = nearby(schedule, e.date)
        add(f"| {e.date} | " + ("; ".join(f"{EVENT_TYPES[s.event_type]} {s.us_date}" for s in near) or "–") + " |")
    add("")
    add(f"- 일정 출처: Fed FOMC 일정, BLS CPI·고용보고서 일정과 공표 기록, 캘리포니아 주무장관실 선거일 안내. 행마다 `verified_at`에 확인일을 적었습니다.")
    add("- 2026년 1~9월 고용보고서 공표일과 기업 실적 발표일은 공식 출처로 확인하지 못해 넣지 않았습니다.")
    add("")


def render(scores_path, provenance_path, events_path, overnight_csv, overnight_provenance, log_path, schedule_path, now=None):
    rows = read_scores(scores_path)
    provenance = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
    if provenance.get("scores_sha256") != hashlib.sha256(Path(scores_path).read_bytes()).hexdigest():
        raise ValueError("Scores do not match provenance; run qsignals.import_scores")
    events = read_events(events_path)
    lines = []
    add = lines.append
    add("# 신호 보강 점검 (사전 등록)")
    add("")
    add("동결 V1·MSI를 바꾸지 않고, 개선 후보 네 가지를 미리 정한 규칙으로만 점검합니다. 결과를 보고 규칙을 바꾸지 않습니다.")
    add("")
    add(f"- 점수 입력: `{provenance['source_repo']}` @ `{(provenance.get('source_git_commit') or '')[:7]}`, {provenance['first_date']} ~ {provenance['last_date']}, 가격 마지막 관측일 {provenance['last_price_date']}")
    add("")
    overnight_section(rows, events, overnight_csv, overnight_provenance, add)
    msi_section(rows, add)
    preopen_section(rows, log_path, add)
    schedule_section(events, schedule_path, add, now)
    add("## 한계")
    add("")
    add("- 1절은 V1 OOS 점수 위에 얹은 실험입니다. README가 요구하는 동결 17개 피처 대비 ablation이 아니므로, 통과해도 배포 저장소에서 다시 검증해야 합니다.")
    add("- 2026년 10월 이후 점수는 walk-forward OOS가 아니라 동결 모델의 사후·운영 추론입니다.")
    add("- 이 보고서의 어떤 결과로도 V1·V2 피처나 기준을 고르지 않습니다.")
    add("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, default=ROOT / "data/input/korea_scores.csv")
    parser.add_argument("--provenance", type=Path, default=ROOT / "data/input/provenance.json")
    parser.add_argument("--events", type=Path, default=ROOT / "data/events/kospi_2026_events.csv")
    parser.add_argument("--overnight", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--overnight-provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--preopen-log", type=Path, default=preopen.DEFAULT_LOG)
    parser.add_argument("--schedule", type=Path, default=ROOT / "data/events/scheduled_us_2026.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "reports/signal_checks.md")
    args = parser.parse_args(argv)
    md = render(args.scores, args.provenance, args.events, args.overnight, args.overnight_provenance,
                args.preopen_log, args.schedule)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
