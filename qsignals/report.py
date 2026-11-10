"""CSV and Korean Markdown output for the event diagnostics."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from bisect import bisect_left
from datetime import datetime, timedelta, timezone

from qsignals.calendar import latest_closed_session

from qsignals.diagnostics import (
    LARGE_DROP_PCT,
    PRE_STRESS_DAYS,
    PRE_WARNING_DAYS,
    VERDICTS,
    WARNING_THRESHOLD,
    EventDiagnosis,
    diagnose_event,
    large_drops,
    summary_by_trigger,
    unlisted_drops,
)
from qsignals.events import TRIGGERS

RECORD_LABELS = {
    "OOS_WALK_FORWARD": "walk-forward OOS",
    "RETROSPECTIVE_INFERENCE": "동결 모델 사후 추론",
    "OPERATIONAL": "동결 모델 운영 추론",
    "NO_SCORE": "점수 없음",
}


@dataclass(frozen=True)
class _Probe:
    """A date to diagnose that is not an annotated event."""

    event_id: str
    date: str
    trigger_primary: str = ""
    reported_change_pct: float | None = None


def write_csv(diagnoses, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    names = [f.name for f in fields(EventDiagnosis)]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for d in diagnoses:
            rec = asdict(d)
            for k, v in rec.items():
                if v is None:
                    rec[k] = ""
                elif isinstance(v, float):
                    rec[k] = f"{v:.6f}"
            writer.writerow(rec)


def _risk(x):
    return "–" if x is None else f"{x * 100:.1f}%"


def _ret(x):
    return "–" if x is None else f"{x:+.2f}%"


def _msi(d):
    if d.msi_on_event is None or d.stress_threshold_on_event is None:
        return "–"
    mark = " ⚑" if d.stress_on_event else ""
    return f"{d.msi_on_event:.2f} / {d.stress_threshold_on_event:.2f}{mark}"


def _int(x):
    return "–" if x is None else str(x)


def _reported(event):
    if event.reported_change_pct is not None:
        return _ret(event.reported_change_pct)
    return event.intraday_note or "–"


def _diagnosis_row(d, first_cols):
    return (
        "| "
        + " | ".join(
            first_cols
            + [
                _ret(d.kospi200_return_pct),
                _risk(d.risk_prev),
                _risk(d.max_risk_pre),
                _int(d.warning_days_pre),
                _msi(d),
                VERDICTS[d.verdict],
            ]
        )
        + " |"
    )


def render_markdown(events, diagnoses, rows, provenance, scan_start):
    by_id = {e.event_id: e for e in events}
    lines = []
    add = lines.append

    add("# 2026 코스피 급락일 × V1 Risk Score 진단")
    add("")
    add(
        "뉴스로 정리한 급락 원인(사후 라벨)을 동결 V1 모델 점수 옆에 놓고, "
        "모델이 급락 **전에** 경보를 냈는지 확인합니다. "
        "**이 라벨은 모델 학습·튜닝에 쓰지 않습니다.**"
    )
    add("")
    add("## 입력")
    add("")
    files = provenance["files"]
    add(
        f"- 점수: `{provenance['source_repo']}` "
        f"`{provenance['source_git_branch']}` @ `{(provenance.get('source_git_commit') or 'unknown')[:7]}`, "
        f"{provenance['first_date']} ~ {provenance['last_date']} ({provenance['rows']:,}행)"
    )
    for key, meta in files.items():
        add(f"  - `{meta['path']}` sha256 `{meta['sha256'][:12]}…`")
    counts = provenance["record_type_counts"]
    add(
        "  - 기록 유형: "
        + ", ".join(f"{RECORD_LABELS[k]} {v:,}행" for k, v in counts.items())
        + f" (동결 모델 학습 기준일 {provenance['training_cutoff']})"
    )
    add(f"  - KOSPI200 가격은 {provenance['last_price_date']}까지만 있습니다.")
    add(f"  - V1 점수 마지막 관측일: {provenance['last_risk_date']}; 한국 원천 생성: {provenance.get('korea_generated_at', '미기록')}")
    if provenance.get("price_source"):
        price = provenance["price_source"]
        add(f"  - 가격 보충: [{price['provider']} {price['symbol']}]({price['url']}), 원응답 sha256 `{price['sha256']}`")
        add(f"  - 동결 가격과 겹치는 {price['frozen_overlap_rows']}일 대조, 최대 절대 차이 {price['frozen_max_abs_difference']:.6f}. 가격은 사건 수익률에만 사용하며 점수·MSI는 바꾸지 않았습니다.")
    add(f"  - 생성 CSV sha256 `{provenance.get('scores_sha256', '미기록')}`")
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9)))
    due = latest_closed_session(now, publication_lag_hours=6)
    add(f"  - 최신성 점검일: {now.date()} KST; 6시간 게시 여유를 적용한 기대 거래일 {due}")
    if provenance["last_risk_date"] < due or provenance["last_price_date"] < due:
        add("  - **갱신 지연**: 기대 거래일까지의 점수 또는 가격이 없습니다. 데이터 마지막 관측일 이후를 정상·무경보로 판정하지 않습니다.")
    gaps = provenance.get("missing_sessions", [])
    add(f"  - KRX 거래일 누락: {len(gaps)}일" + (f" ({', '.join(gaps)})" if gaps else ""))
    add("- 이벤트: `data/events/kospi_2026_events.csv` (보도 기준 KOSPI 등락, 사후 정리)")
    add("")
    add("## 판정 기준 (고정)")
    add("")
    add(f"- 경보: V1 Risk Score ≥ {WARNING_THRESHOLD:.2f} (운영 기준 그대로)")
    add(
        f"- **{VERDICTS['IN_STRESS']}**: 급락 직전 {PRE_STRESS_DAYS}거래일 중 "
        "MSI가 공식 Stress 기준 이상인 날이 있음. 이미 스트레스 구간이므로 '사전' 경보 판정 대상이 아님"
    )
    add(
        f"- **{VERDICTS['WARNED']}**: 위 경우가 아니고, 직전 {PRE_WARNING_DAYS}거래일 중 경보가 하루 이상"
    )
    add(f"- **{VERDICTS['MISSED']}**: 둘 다 아님")
    add(
        f"- **{VERDICTS['INCOMPLETE']}** / **{VERDICTS['NO_DATA']}**: "
        "직전 구간 점수 결측 / 급락일이 점수 데이터에 없음"
    )
    add("- 급락 당일 점수는 당일 종가까지 반영하므로 '사전' 판정에 쓰지 않습니다.")
    add("- 직전 구간은 별도 KRX 거래일 달력으로 확인합니다. 행 전체가 빠져도 결측으로 처리하며, 여러 거래일 간 수익률을 하루 수익률로 표시하지 않습니다.")
    add("- ⚑ = 급락 당일 MSI가 Stress 기준 이상 (Stress Event)")
    add("")

    add("## 이벤트별 결과")
    add("")
    add(
        "| 날짜 | 트리거 | 보도 등락 (KOSPI) | 데이터 KOSPI200 | 전일 위험도 | "
        f"직전 {PRE_WARNING_DAYS}일 최고 | 경보일 | 당일 MSI / 기준 | 판정 | 뉴스 출처 |"
    )
    add("|---|---|---:|---:|---:|---:|---:|---:|---|---|")
    for d in diagnoses:
        e = by_id[d.event_id]
        quality = "출처 미확인" if e.source_quality == "unsourced" else e.source_quality
        add(_diagnosis_row(d, [d.date, TRIGGERS[e.trigger_primary], _reported(e)]) + f" {quality} |")
    add("")
    retro = [d.date for d in diagnoses if d.record_type in ("RETROSPECTIVE_INFERENCE", "OPERATIONAL")]
    if retro:
        add(
            f"- {', '.join(retro)}: walk-forward OOS가 아니라 "
            f"{provenance['training_cutoff']}까지 학습한 동결 모델의 추론값입니다. "
            "2026년 10월은 팀 규칙상 튜닝 금지 홀드아웃입니다."
        )
    missing = [d.date for d in diagnoses if d.verdict == "NO_DATA"]
    if missing:
        add(f"- {', '.join(missing)}: 진단 가능한 거래일 자료가 없어 판정하지 못했습니다. 입력 마지막 관측일은 {provenance['last_date']}입니다.")
    add("")

    add("## 트리거 유형별 요약")
    add("")
    order = ["WARNED", "IN_STRESS", "MISSED", "INCOMPLETE", "NO_DATA"]
    add("| 트리거 | 건수 | " + " | ".join(VERDICTS[v] for v in order) + " |")
    add("|---|---:|" + "---:|" * len(order))
    table = summary_by_trigger(diagnoses)
    for key in TRIGGERS:
        if key not in table:
            continue
        c = table[key]
        add(
            f"| {TRIGGERS[key]} | {sum(c.values())} | "
            + " | ".join(str(c.get(v, 0)) for v in order)
            + " |"
        )
    add("")
    sizes = [sum(c.values()) for c in table.values()]
    add(
        f"유형별 건수가 {min(sizes)}~{max(sizes)}건이라 비율로 일반화할 수 없습니다. "
        "어떤 유형에서 경보가 비었는지 보는 기술 통계입니다."
        if sizes else "이벤트 주석이 없습니다. 아래 가격 기반 급락일 조사는 계속합니다."
    )
    add("")

    drops = large_drops(rows, LARGE_DROP_PCT, scan_start)
    extra = unlisted_drops(drops, events)
    add(f"## 뉴스 목록에 없는 급락일 (KOSPI200 {LARGE_DROP_PCT:.0f}% 이하)")
    add("")
    add(
        f"{scan_start} 이후 가격 데이터({provenance['last_price_date']}까지)에서 "
        f"종가 기준 {LARGE_DROP_PCT:.0f}% 이하 하락일은 {len(drops)}일이고, "
        f"그중 {len(extra)}일은 뉴스 목록에 없습니다. "
        "급락 사례를 뉴스로 고르면 기사화된 날만 남으므로, 진단 대상은 가격 데이터로 고르는 편이 안전합니다."
    )
    add("")
    if extra:
        add(
            f"| 날짜 | 데이터 KOSPI200 | 전일 위험도 | 직전 {PRE_WARNING_DAYS}일 최고 | 경보일 | "
            "당일 MSI / 기준 | 판정 |"
        )
        add("|---|---:|---:|---:|---:|---:|---|")
        index = {r.date: i for i, r in enumerate(rows)}
        for date, _ in extra:
            d = diagnose_event(_Probe(event_id=f"DROP-{date}", date=date), rows, index)
            add(_diagnosis_row(d, [date]))
        add("")

    add("## 한계")
    add("")
    add("- 트리거 라벨은 급락 이후 보도를 정리한 사후 해석이며, 출처가 없는 이벤트도 있습니다(`source_quality=unsourced`).")
    add("- 보도 등락은 KOSPI, 데이터 수익률은 KOSPI200이라 수치가 다릅니다.")
    add("- 이 진단은 모델을 바꾸지 않습니다. 결과를 보고 피처·기준을 고르면 홀드아웃 규칙을 깨게 됩니다.")
    add("")
    return "\n".join(lines)
