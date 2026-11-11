"""Does the official Korea MSI recognize large KOSPI200 drops as stress?

Diagnostic only. The official MSI comes from the frozen research project and
defines the Target_10D label, so it is never edited here. This module measures
two suspected failure mechanisms and a candidate drawdown channel, using the
2016-2025 design period only; 2026 is reported separately as a holdout.
"""

from __future__ import annotations

from bisect import bisect_left, insort
from dataclasses import dataclass

from qsignals.calendar import load_sessions

DESIGN_END = "2025-12-31"
HOLDOUT_START = "2026-01-01"
DROP_PCT = -3.0           # one consecutive-session KOSPI200 return
EQUITY_WINDOW = 21        # MSI equity channel horizon (sessions)
PEAK_WINDOW = 252         # drawdown measured from the trailing one-year high
MIN_HISTORY = 250         # past drawdown observations before a percentile is used
DRAWDOWN_PCT = 0.10       # candidate flag: drawdown among the worst 10% seen so far
# Pre-registered reading: the evidence supports proposing an MSI revision in the
# deployment repository if the official MSI misses at least 30% of design
# drops and the drawdown channel recovers at least half of those misses while
# flagging at most 15% of all design sessions.
MISS_SHARE_MIN = 0.30
RECOVER_SHARE_MIN = 0.50
FLAG_RATE_MAX = 0.15


@dataclass(frozen=True)
class DayCheck:
    date: str
    ret_pct: float | None
    ret21_pct: float | None
    drawdown_pct: float | None
    drawdown_rank: float | None
    official: bool | None
    drawdown_flag: bool | None


def daily_checks(rows, sessions=None):
    """One record per priced KRX session, with past-only drawdown percentiles."""
    sessions = sessions or load_sessions()
    priced = [r for r in rows if r.kospi200_close is not None]
    index = {d: i for i, d in enumerate(sessions)}
    out, history = [], []
    for i, r in enumerate(priced):
        consecutive = i > 0 and index.get(r.date, -2) - index.get(priced[i - 1].date, -9) == 1
        ret = (r.kospi200_close / priced[i - 1].kospi200_close - 1) * 100 if consecutive else None
        ret21 = dd = rank = None
        start = i - EQUITY_WINDOW
        if start >= 0 and index.get(r.date, 0) - index.get(priced[start].date, 0) == EQUITY_WINDOW:
            ret21 = (r.kospi200_close / priced[start].kospi200_close - 1) * 100
        lo = i - PEAK_WINDOW + 1
        if lo >= 0 and index.get(r.date, 0) - index.get(priced[lo].date, 0) == PEAK_WINDOW - 1:
            dd = (r.kospi200_close / max(p.kospi200_close for p in priced[lo:i + 1]) - 1) * 100
            if len(history) >= MIN_HISTORY:
                rank = bisect_left(history, dd + 1e-12) / len(history)  # share of past days at least this deep
            insort(history, dd)
        official = None if r.msi is None or r.stress_threshold is None else r.msi >= r.stress_threshold
        out.append(DayCheck(r.date, ret, ret21, dd, rank, official, None if rank is None else rank <= DRAWDOWN_PCT))
    return out


def _period(checks, first, last):
    days = [c for c in checks if first <= c.date <= last]
    drops = [c for c in days if c.ret_pct is not None and c.ret_pct <= DROP_PCT]
    judged = [c for c in drops if c.official is not None]
    missed = [c for c in judged if not c.official]
    with_dd = [c for c in missed if c.drawdown_flag is not None]
    recovered = [c for c in with_dd if c.drawdown_flag]
    official_days = [c for c in days if c.official is not None]
    dd_days = [c for c in days if c.drawdown_flag is not None]
    return {
        "range": (days[0].date, days[-1].date) if days else None,
        "drops": drops, "judged": len(judged), "missed": len(missed),
        "rally_offset": sum(c.ret21_pct is not None and c.ret21_pct > 0 for c in missed),
        "missed_with_drawdown": len(with_dd), "recovered": len(recovered),
        "official_flag_rate": sum(c.official for c in official_days) / len(official_days) if official_days else None,
        "drawdown_flag_rate": sum(c.drawdown_flag for c in dd_days) / len(dd_days) if dd_days else None,
    }


def run(rows):
    checks = daily_checks(rows)
    design = _period(checks, "0000-00-00", DESIGN_END)
    holdout = _period(checks, HOLDOUT_START, "9999-99-99")
    years = {}
    for c in checks:
        if c.official is not None:
            years.setdefault(c.date[:4], []).append(c.official)
    miss_share = design["missed"] / design["judged"] if design["judged"] else None
    recover_share = design["recovered"] / design["missed_with_drawdown"] if design["missed_with_drawdown"] else None
    supported = (miss_share is not None and recover_share is not None and design["drawdown_flag_rate"] is not None
                 and miss_share >= MISS_SHARE_MIN and recover_share >= RECOVER_SHARE_MIN
                 and design["drawdown_flag_rate"] <= FLAG_RATE_MAX)
    return {"design": design, "holdout": holdout, "miss_share": miss_share, "recover_share": recover_share,
            "official_rate_by_year": {y: sum(v) / len(v) for y, v in sorted(years.items())},
            "status": "revision_supported" if supported else "not_supported"}
