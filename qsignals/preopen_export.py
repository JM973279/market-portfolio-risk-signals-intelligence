"""Write frontend/public/data/korea-preopen.json: the pre-open US reference for Korea.

    python3 -m qsignals.preopen_export [--check]

Display only. The frozen V1 Risk Score and MSI are unchanged and nothing here
feeds a score (README ①, reports/signal_checks.md section 1).

- latest/history: EWY and ^SOX close-to-close returns of the last US session
  before each KRX session, from the stored data/input/overnight_us.csv
  (verified against its provenance hash). Returns only: no prices are exported.
- context: how KOSPI200 moved on KRX sessions after each EWY range, counted
  only in the design period (through overnight_eval.DESIGN_END). The 2026
  holdout is never used here. It is a historical frequency, not a forecast.

Written by the "Refresh overnight US prices" workflow in the same commit as the
overnight prices, so the two never disagree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from qsignals.calendar import load_sessions
from qsignals.overnight import DEFAULT_CSV, DEFAULT_PROVENANCE, align, read_overnight
from qsignals.overnight_eval import DESIGN_END
from qsignals.scores import read_scores

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "frontend/public/data/korea-preopen.json"
SCORES = ROOT / "data/input/korea_scores.csv"
HISTORY_SESSIONS = 20
DROP = -0.02  # same "next session -2% or worse" label as the pre-registered check
# EWY ranges, fixed before looking at any 2026 data. (low, high]: low < r <= high.
BUCKETS = (
    ("le_-3", None, -0.03),
    ("-3_-1", -0.03, -0.01),
    ("-1_1", -0.01, 0.01),
    ("1_3", 0.01, 0.03),
    ("gt_3", 0.03, None),
)


def bucket_of(r):
    for key, low, high in BUCKETS:
        if (low is None or r > low) and (high is None or r <= high):
            return key
    raise ValueError(f"No bucket for {r}")


def _r(x):
    return None if x is None else round(x, 6)


def kospi_returns(score_rows, sessions):
    """KOSPI200 close-to-close return per KRX session, only across consecutive calendar sessions."""
    closes = {r.date: r.kospi200_close for r in score_rows if r.kospi200_close is not None}
    out = {}
    for prev, day in zip(sessions, sessions[1:]):
        if prev in closes and day in closes:
            out[day] = closes[day] / closes[prev] - 1.0
    return out


def context(aligned, kospi):
    days = [d for d in sorted(aligned) if d <= DESIGN_END and d in kospi and aligned[d].returns.get("EWY") is not None]
    if not days:
        raise ValueError("No design-period sessions with both EWY and KOSPI200 returns")
    groups = {key: [] for key, _, _ in BUCKETS}
    for d in days:
        groups[bucket_of(aligned[d].returns["EWY"])].append(kospi[d])

    def stats(rets):
        rets = sorted(rets)
        n = len(rets)
        return {"sessions": n,
                "drop_share": _r(sum(x <= DROP for x in rets) / n) if n else None,
                "median_return": _r((rets[(n - 1) // 2] + rets[n // 2]) / 2) if n else None}

    return {"period": {"first": days[0], "last": days[-1]}, "drop_threshold": DROP,
            "all": stats([kospi[d] for d in days]),
            "buckets": [{"key": key, "low": low, "high": high, **stats(groups[key])} for key, low, high in BUCKETS]}


def build(csv_path=DEFAULT_CSV, provenance_path=DEFAULT_PROVENANCE, scores_path=SCORES):
    rows, meta = read_overnight(csv_path, provenance_path)
    if rows is None:
        raise FileNotFoundError("Overnight prices missing: run qsignals.overnight_refresh in Actions first")
    sessions = load_sessions()
    aligned = align(sessions, rows, meta)
    if not aligned:
        raise ValueError("No KRX session has a complete preceding US session")
    tickers = list(meta["tickers"])

    def point(day):
        o = aligned[day]
        return {"krxDate": day, "usDate": o.us_date, "returns": {t: _r(o.returns[t]) for t in tickers},
                "ewyRange": None if o.returns.get("EWY") is None else bucket_of(o.returns["EWY"])}

    recent = sorted(aligned)[-HISTORY_SESSIONS:]
    return {
        "schema_version": 1,
        "is_forecast": False,
        "use": "display only; frozen V1 Risk Score and MSI unchanged",
        "tickers": tickers,
        "source": {"path": "data/input/overnight_us.csv", "sha256": meta["sha256"], "provider": meta.get("provider"),
                   "retrievedAt": meta.get("retrieved_at"), "lastUsSession": meta["last_date"],
                   "nextUsSession": meta["next_us_session"]},
        "latest": point(recent[-1]),
        "history": [point(d) for d in reversed(recent)],
        "context": context(aligned, kospi_returns(read_scores(scores_path, "korea"), sessions)),
        "report": "reports/signal_checks.md",
    }


def render(export):
    return json.dumps(export, indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if the frontend export is stale")
    args = parser.parse_args(argv)
    text = render(build())
    name = OUTPUT.relative_to(ROOT)
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{name} is stale; run python3 -m qsignals.preopen_export", file=sys.stderr)
            return 1
        print(f"{name} is current.")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {name} (latest KRX {json.loads(text)['latest']['krxDate']}, sha256 "
          f"{hashlib.sha256(text.encode()).hexdigest()[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
