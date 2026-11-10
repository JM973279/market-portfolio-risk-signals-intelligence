"""Per-event diagnosis: did the frozen V1 model warn before each sell-off?

All windows are counted in trading observations of the score series, and the
event day itself is never part of a "before" window: the score on day t uses
data through t's close, so it cannot be an advance warning for t.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

# Frozen V1 operational threshold (market_engine/early_warning_v2/EXPERIMENTS.md).
WARNING_THRESHOLD = 0.50
# Matches the Target_10D horizon: a warning on t-10..t-1 covers day t.
PRE_WARNING_DAYS = 10
# MSI at or above the official threshold on t-5..t-1 means the sell-off
# happened inside an existing stress episode rather than starting one.
PRE_STRESS_DAYS = 5
# Reporting filter for the systematic large-decline scan.
LARGE_DROP_PCT = -5.0

VERDICTS = {
    "NO_DATA": "데이터 없음",
    "INCOMPLETE": "직전 구간 결측",
    "IN_STRESS": "스트레스 진행 중 추가 급락",
    "WARNED": "사전 경보 있음",
    "MISSED": "사전 경보 없음",
}


@dataclass(frozen=True)
class EventDiagnosis:
    event_id: str
    date: str
    trigger_primary: str
    record_type: str | None
    window_record_types: str | None
    kospi200_return_pct: float | None
    reported_change_pct: float | None
    risk_prev: float | None
    risk_on_event: float | None
    max_risk_pre: float | None
    warning_days_pre: int | None
    warning_streak_prev: int | None
    stress_days_pre: int | None
    msi_on_event: float | None
    stress_threshold_on_event: float | None
    stress_on_event: bool | None
    verdict: str


def pct_return(rows, i):
    if i <= 0:
        return None
    before, now = rows[i - 1].kospi200_close, rows[i].kospi200_close
    if before is None or now is None:
        return None
    return (now / before - 1.0) * 100.0


def is_stress(row):
    if row.msi is None or row.stress_threshold is None:
        return None
    return row.msi >= row.stress_threshold


def diagnose_event(event, rows, index=None):
    if index is None:
        index = {r.date: i for i, r in enumerate(rows)}

    i = index.get(event.date)
    if i is None:
        return EventDiagnosis(
            event_id=event.event_id,
            date=event.date,
            trigger_primary=event.trigger_primary,
            record_type=None,
            window_record_types=None,
            kospi200_return_pct=None,
            reported_change_pct=event.reported_change_pct,
            risk_prev=None,
            risk_on_event=None,
            max_risk_pre=None,
            warning_days_pre=None,
            warning_streak_prev=None,
            stress_days_pre=None,
            msi_on_event=None,
            stress_threshold_on_event=None,
            stress_on_event=None,
            verdict="NO_DATA",
        )

    row = rows[i]
    pre = rows[max(0, i - PRE_WARNING_DAYS):i]
    pre_stress = rows[max(0, i - PRE_STRESS_DAYS):i]
    risks = [r.risk_v1 for r in pre]
    stress_flags = [is_stress(r) for r in pre_stress]

    complete = (
        len(pre) == PRE_WARNING_DAYS
        and all(x is not None for x in risks)
        and all(x is not None for x in stress_flags)
    )

    max_risk = warning_days = streak = stress_days = None
    if complete:
        max_risk = max(risks)
        warning_days = sum(x >= WARNING_THRESHOLD for x in risks)
        streak = 0
        for x in reversed(risks):
            if x < WARNING_THRESHOLD:
                break
            streak += 1
        stress_days = sum(stress_flags)

    if not complete:
        verdict = "INCOMPLETE"
    elif stress_days > 0:
        verdict = "IN_STRESS"
    elif warning_days > 0:
        verdict = "WARNED"
    else:
        verdict = "MISSED"

    return EventDiagnosis(
        event_id=event.event_id,
        date=event.date,
        trigger_primary=event.trigger_primary,
        record_type=row.record_type,
        window_record_types=";".join(sorted({r.record_type for r in pre})) or None,
        kospi200_return_pct=pct_return(rows, i),
        reported_change_pct=event.reported_change_pct,
        risk_prev=rows[i - 1].risk_v1 if i > 0 else None,
        risk_on_event=row.risk_v1,
        max_risk_pre=max_risk,
        warning_days_pre=warning_days,
        warning_streak_prev=streak,
        stress_days_pre=stress_days,
        msi_on_event=row.msi,
        stress_threshold_on_event=row.stress_threshold,
        stress_on_event=is_stress(row),
        verdict=verdict,
    )


def diagnose_all(events, rows):
    index = {r.date: i for i, r in enumerate(rows)}
    return [diagnose_event(e, rows, index) for e in events]


def large_drops(rows, threshold_pct=LARGE_DROP_PCT, start_date=None):
    """Trading days whose KOSPI200 close-to-close return is <= threshold_pct."""

    out = []
    for i in range(1, len(rows)):
        if start_date and rows[i].date < start_date:
            continue
        ret = pct_return(rows, i)
        if ret is not None and ret <= threshold_pct:
            out.append((rows[i].date, ret))
    return out


def unlisted_drops(drops, events):
    listed = {e.date for e in events}
    return [(d, r) for d, r in drops if d not in listed]


def summary_by_trigger(diagnoses):
    table = {}
    for d in diagnoses:
        table.setdefault(d.trigger_primary, Counter())[d.verdict] += 1
    return table
