"""Pre-registered overlay experiment: do overnight US prices add to frozen V1?

The question is narrow: at the KRX open of day t+1, does adding the preceding
US session (EWY, ^SOX) to the frozen V1 score at t's close improve detection
of a next-session KOSPI200 drop? This is a stacked overlay on V1's OOS output,
not the 17-feature purged ablation the README requires before a model change.
Passing it makes the signal a candidate to bring to the deployment repository;
nothing here changes V1, MSI or thresholds.

Every constant below is fixed before results are seen. 2026 is a holdout that
is reported but never used to choose anything.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

from qsignals.calendar import load_sessions
from qsignals.overnight import TICKERS, align
from qsignals.stats import Logistic, average_precision, block_bootstrap_diff, recall_at_top

DESIGN_END = "2025-12-31"
HOLDOUT_START = "2026-01-01"
LABELS = {"drop2": -2.0, "drop3": -3.0}
PRIMARY_LABEL = "drop2"
INITIAL_TRAIN = 750      # about three years of OOS observations
STEP = 21                # refit monthly, like V1
PURGE = 1                # last training label overlaps the first test day's information set
L2 = 1.0
BOOTSTRAP_REPS = 2000
SEED = 20261111
# Decision rule: the primary comparison passes if the 95% interval of the
# AP gain of the full overnight model over the base model is entirely above 0.
PRIMARY_COMPARISON = ("base", "overnight_full")


@dataclass(frozen=True)
class Sample:
    date: str          # KRX day t (decision made before the open of t+1)
    target_date: str   # KRX day t+1
    record_type: str
    v1: float
    krx_ret: float     # KOSPI200 return on t, already known at the decision
    overnight: dict    # ticker -> US session return before t+1
    next_ret: float    # KOSPI200 return t -> t+1 (percent)


def model_features(tickers):
    return {
        "base": ("v1", "krx_ret"),
        "overnight_" + tickers[0]: ("v1", "krx_ret", tickers[0]),
        "overnight_full": ("v1", "krx_ret", *tickers),
    }


def build_samples(rows, overnight_rows, provenance, tickers=TICKERS, sessions=None):
    sessions = sessions or load_sessions()
    by_date = {r.date: r for r in rows}
    aligned = align(sessions, overnight_rows, provenance, tickers)
    out = []
    for r in rows:
        pos = bisect_left(sessions, r.date)
        if r.risk_v1 is None or pos == 0 or pos + 1 >= len(sessions) or sessions[pos] != r.date:
            continue
        prev, nxt = by_date.get(sessions[pos - 1]), by_date.get(sessions[pos + 1])
        if not prev or not nxt or None in (prev.kospi200_close, r.kospi200_close, nxt.kospi200_close):
            continue  # consecutive KRX sessions only; no multi-day returns
        o = aligned.get(nxt.date)
        if o is None or any(o.returns.get(t) is None for t in tickers):
            continue
        out.append(Sample(
            date=r.date, target_date=nxt.date, record_type=r.record_type, v1=r.risk_v1,
            krx_ret=(r.kospi200_close / prev.kospi200_close - 1.0) * 100.0,
            overnight={t: o.returns[t] * 100.0 for t in tickers},
            next_ret=(nxt.kospi200_close / r.kospi200_close - 1.0) * 100.0,
        ))
    return out


def _x(samples, names):
    return [[s.v1 if n == "v1" else s.krx_ret if n == "krx_ret" else s.overnight[n] for n in names] for s in samples]


def _y(samples, label):
    return [1 if s.next_ret <= LABELS[label] else 0 for s in samples]


def walk_forward(samples, names, label):
    y = _y(samples, label)
    preds, warm = [None] * len(samples), None
    for start in range(INITIAL_TRAIN, len(samples), STEP):
        train = slice(0, start - PURGE)
        if sum(y[train]) < 5:
            continue
        model = Logistic(l2=L2).fit(_x(samples[train], names), y[train], warm=warm)
        warm = model.coef
        end = min(start + STEP, len(samples))
        preds[start:end] = model.predict(_x(samples[start:end], names))
    return preds


def _metrics(scores, labels):
    return {"n": len(labels), "positives": sum(labels), "base_rate": sum(labels) / len(labels) if labels else None,
            "ap": average_precision(scores, labels), "recall_top10": recall_at_top(scores, labels)}


def run(rows, overnight_rows, provenance, tickers=TICKERS, reps=BOOTSTRAP_REPS):
    tickers = tuple(tickers)
    samples = build_samples(rows, overnight_rows, provenance, tickers)
    design = [s for s in samples if s.date <= DESIGN_END and s.record_type == "OOS_WALK_FORWARD"]
    holdout = [s for s in samples if s.date >= HOLDOUT_START]
    models = model_features(tickers)
    result = {"tickers": list(tickers), "design_samples": len(design), "holdout_samples": len(holdout),
              "design_range": (design[0].date, design[-1].date) if design else None,
              "holdout_range": (holdout[0].date, holdout[-1].date) if holdout else None,
              "labels": {}, "events": {}}
    if len(design) <= INITIAL_TRAIN + STEP:
        result["status"] = "insufficient_design_samples"
        return result
    for label in LABELS:
        preds = {name: walk_forward(design, names, label) for name, names in models.items()}
        keep = [i for i in range(len(design)) if all(p[i] is not None for p in preds.values())]
        y = [_y(design, label)[i] for i in keep]
        if not keep or sum(y) == 0:
            result["labels"][label] = {"status": "insufficient_positives"}
            continue
        scored = {name: [p[i] for i in keep] for name, p in preds.items()}
        months = [design[i].date[:7] for i in keep]
        entry = {"oos_range": (design[keep[0]].date, design[keep[-1]].date),
                 "oos": {name: _metrics(s, y) for name, s in scored.items()}, "gain": {}}
        for name in models:
            if name != "base":
                low, high, share = block_bootstrap_diff(months, scored["base"], scored[name], y, reps=reps, seed=SEED)
                entry["gain"][name] = {"ap_gain": entry["oos"][name]["ap"] - entry["oos"]["base"]["ap"],
                                       "ci_low": low, "ci_high": high, "share_no_gain": share}
        fitted = {name: Logistic(l2=L2).fit(_x(design, names), _y(design, label)) for name, names in models.items()}
        if holdout:
            hy = _y(holdout, label)
            hp = {name: m.predict(_x(holdout, models[name])) for name, m in fitted.items()}
            entry["holdout"] = {name: _metrics(p, hy) if sum(hy) else {"n": len(hy), "positives": 0} for name, p in hp.items()}
            if label == PRIMARY_LABEL:
                result["events"] = {s.target_date: {"overnight": s.overnight, "next_ret": s.next_ret, "v1": s.v1,
                                                     "prob": {name: hp[name][i] for name in models}}
                                    for i, s in enumerate(holdout)}
        result["labels"][label] = entry
    primary = result["labels"][PRIMARY_LABEL]
    if primary.get("status") == "insufficient_positives":
        result["status"] = "insufficient_positives"
        return result
    gain = primary["gain"][PRIMARY_COMPARISON[1]]
    result["status"] = "candidate" if gain["ci_low"] is not None and gain["ci_low"] > 0 else "not_supported"
    return result
