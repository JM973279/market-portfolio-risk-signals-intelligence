"""Build the Korea and US historical scenario libraries shown on the Scenario Analysis page.

Read-only: combines curated qualitative inputs (korea_episodes.json) with stored
KOSPI200 prices and frozen V1 / MSI values already exported for the dashboard.
It never runs a model, never fills missing values and never forecasts.

    python -m market_engine.scenarios.build_korea_library          # write both exports
    python -m market_engine.scenarios.build_korea_library --check  # fail if an export is stale
    python -m market_engine.scenarios.build_korea_library --market us   # one market only
"""
import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EPISODES_PATH = ROOT / "market_engine/scenarios/korea_episodes.json"
GLOBAL_PATH = ROOT / "frontend/public/data/global-markets.json"
OPERATIONAL_PATH = ROOT / "frontend/public/data/operational-markets.json"
OUTPUT_PATH = ROOT / "frontend/public/data/korea-scenarios.json"
# Same rules for both markets; each market reads only its own stored prices and model values.
MARKETS = {
    "korea": {"episodes": EPISODES_PATH, "output": OUTPUT_PATH, "index": "KOSPI200"},
    "us": {"episodes": ROOT / "market_engine/scenarios/us_episodes.json",
           "output": ROOT / "frontend/public/data/us-scenarios.json", "index": "SPY"},
}

# Fixed before looking at any result; not tuned per episode.
WINDOW_SESSIONS = 60          # trough search window, onset day included
PRIOR_SESSIONS = 10           # V1 warning count before onset
WARN_AT = 0.50                # same V1 decision threshold as the dashboard
BORDERLINE_AT = 0.40
GEOS = {"foreign", "domestic", "both"}
TIERS = {"core", "supporting"}


def sha256(path):
    # Hash with LF line endings so a Windows checkout (CRLF) gives the same value as CI.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def finite(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def load_market(market="korea"):
    """Return (sessions, price, model) where model maps date -> V1/MSI values and their origin."""
    snapshot = json.loads(GLOBAL_PATH.read_text(encoding="utf-8"))
    operational = json.loads(OPERATIONAL_PATH.read_text(encoding="utf-8"))
    price, model = {}, {}
    for point in snapshot[market]:
        if finite(point.get("price")) is not None:
            price[point["date"]] = point["price"]
        model[point["date"]] = {
            "risk": finite(point.get("risk")),
            "msi": finite(point.get("msi")),
            "threshold": finite(point.get("threshold")),
            "origin": "historical_oos",
        }
    for point in operational["markets"][market]["history"]:
        current = model.get(point["date"])
        # Historical OOS values win; operational rows only fill dates the snapshot lacks.
        if current is None or all(current[k] is None for k in ("risk", "msi", "threshold")):
            model[point["date"]] = {
                "risk": finite(point.get("risk")),
                "msi": finite(point.get("msi")),
                "threshold": finite(point.get("threshold")),
                "origin": point.get("recordType", "operational").lower(),
            }
    sessions = sorted(set(price) | set(model))
    return sessions, price, model


def verdict(risk):
    if risk is None:
        return "no_data"
    if risk >= WARN_AT:
        return "warned"
    if risk >= BORDERLINE_AT:
        return "borderline"
    return "missed"


def price_metrics(onset, priced):
    """Drawdown path from the close before onset. Missing prices make the metrics null."""
    dates = sorted(priced)
    if onset not in priced:
        return None, "price_missing"
    i = dates.index(onset)
    if i == 0:
        return None, "price_missing"
    ref_date, ref = dates[i - 1], priced[dates[i - 1]]
    window = dates[i:i + WINDOW_SESSIONS]
    trough_date = min(window, key=lambda d: priced[d])
    trough_index = dates.index(trough_date)
    recovery_date = next((d for d in dates[trough_index + 1:] if priced[d] >= ref), None)
    return {
        "reference_date": ref_date,
        "onset_return": round(priced[onset] / ref - 1, 6),
        "max_drawdown": round(priced[trough_date] / ref - 1, 6),
        "trough_date": trough_date,
        "sessions_to_trough": trough_index - (i - 1),
        "recovery_date": recovery_date,
        "sessions_to_recover": None if recovery_date is None else dates.index(recovery_date) - trough_index,
        "window_sessions": len(window),
        "window_end_date": window[-1],
        "window_complete": len(window) == WINDOW_SESSIONS,
        "trough_at_window_end": trough_date == window[-1] and len(window) == WINDOW_SESSIONS,
        "price_last_date": dates[-1],
    }, None


def model_metrics(onset, sessions, model):
    if onset not in sessions:
        return {"verdict": "no_data", "prior_risk": None, "prior_date": None, "prior_warning_sessions": None,
                "prior_observed_sessions": 0, "msi": None, "threshold": None, "msi_recognized": None, "origin": None}
    i = sessions.index(onset)
    prior = sessions[max(0, i - PRIOR_SESSIONS):i]
    prior_risk = [model.get(d, {}).get("risk") for d in prior]
    last = prior[-1] if prior else None
    risk = model.get(last, {}).get("risk") if last else None
    today = model.get(onset, {})
    msi, threshold = today.get("msi"), today.get("threshold")
    return {
        "verdict": verdict(risk),
        "prior_risk": risk,
        "prior_date": last,
        "prior_warning_sessions": sum(r is not None and r >= WARN_AT for r in prior_risk),
        "prior_observed_sessions": sum(r is not None for r in prior_risk),
        "msi": msi,
        "threshold": threshold,
        "msi_recognized": None if msi is None or threshold is None else msi >= threshold,
        "origin": model.get(last, {}).get("origin") if last else None,
    }


def summarize(episodes, categories):
    rows = []
    for key in categories:
        group = [e for e in episodes if e["category"] == key]
        if not group:
            continue
        drawdowns = [e["metrics"]["max_drawdown"] for e in group if e["metrics"]]
        judged = [e for e in group if e["model"]["verdict"] != "no_data"]
        rows.append({
            "category": key,
            "episodes": len(group),
            "with_prices": len(drawdowns),
            "median_max_drawdown": round(statistics.median(drawdowns), 6) if drawdowns else None,
            "worst_max_drawdown": round(min(drawdowns), 6) if drawdowns else None,
            "warned": sum(e["model"]["verdict"] == "warned" for e in judged),
            "judged": len(judged),
        })
    return rows


def validate(curated):
    categories = curated["categories"]
    ids = [e["id"] for e in curated["episodes"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate episode id")
    onsets = [e["onset"] for e in curated["episodes"]]
    if onsets != sorted(onsets):
        raise ValueError("episodes must be in onset order")
    for e in curated["episodes"]:
        if e["category"] not in categories:
            raise ValueError(f"{e['id']}: unknown category {e['category']}")
        if e["geo"] not in GEOS or e["tier"] not in TIERS:
            raise ValueError(f"{e['id']}: invalid geo or tier")
        for field in ("name", "cause"):
            if not (e[field].get("en") and e[field].get("ko")):
                raise ValueError(f"{e['id']}: bilingual {field} required")
        if e["source"] is not None and not e["source"]["url"].startswith("https://"):
            raise ValueError(f"{e['id']}: source must be https")


def build(market="korea"):
    spec = MARKETS[market]
    curated = json.loads(spec["episodes"].read_text(encoding="utf-8"))
    validate(curated)
    sessions, price, model = load_market(market)
    episodes = []
    for e in curated["episodes"]:
        metrics, missing = price_metrics(e["onset"], price)
        notes = []
        if missing:
            notes.append(missing)
        elif not metrics["window_complete"]:
            notes.append("window_incomplete")
        elif metrics["trough_at_window_end"]:
            notes.append("trough_at_window_end")
        if e["source"] is None:
            notes.append("source_unverified")
        episodes.append({**e, "metrics": metrics, "model": model_metrics(e["onset"], sessions, model), "notes": notes})
    for e in episodes:
        m = e["metrics"]
        later = [o["id"] for o in episodes if m and e["onset"] < o["onset"] <= m["window_end_date"]]
        e["overlaps"] = later
        if later:
            e["notes"].append("window_overlaps")
    return {
        "schema_version": 1,
        "asOf": max(price),
        "is_forecast": False,
        "parameters": {
            "selection": f"{spec['index']} one-session return <= -3% or <= -10% within ten sessions, clustered into episodes.",
            "window_sessions": WINDOW_SESSIONS,
            "prior_sessions": PRIOR_SESSIONS,
            "verdict_rule": {"warned": f"prior-session V1 >= {WARN_AT}", "borderline": f"{BORDERLINE_AT} <= prior-session V1 < {WARN_AT}", "missed": f"prior-session V1 < {BORDERLINE_AT}"},
            "drawdown_reference": "close of the session before onset",
            "note_codes": {
                "price_missing": "KOSPI200 price for the onset date is not in the repository snapshot.",
                "window_incomplete": f"Fewer than {WINDOW_SESSIONS} sessions after onset are stored; the low may not be final.",
                "trough_at_window_end": "The low falls on the last session of the window; the decline may have continued.",
                "source_unverified": "Source link not yet verified for this episode.",
                "window_overlaps": "The drawdown window includes later episodes listed in overlaps.",
            },
        },
        "taxonomy": curated["taxonomy"],
        "categories": curated["categories"],
        "sources": {
            "episodes": {"path": spec["episodes"].relative_to(ROOT).as_posix(), "sha256": sha256(spec["episodes"])},
            "prices_and_model": {"path": GLOBAL_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(GLOBAL_PATH)},
            "operational": {"path": OPERATIONAL_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(OPERATIONAL_PATH)},
        },
        "summary": summarize(episodes, curated["categories"]),
        "episodes": episodes,
    }


def render(library):
    return json.dumps(library, indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if a stored export differs")
    parser.add_argument("--market", choices=[*MARKETS, "all"], default="all")
    args = parser.parse_args(argv)
    status = 0
    for market in (MARKETS if args.market == "all" else [args.market]):
        output = MARKETS[market]["output"]
        text = render(build(market))
        if args.check:
            stored = output.read_text(encoding="utf-8") if output.exists() else ""
            if stored != text:
                print(f"{output.name} is stale; rerun build_korea_library.", file=sys.stderr)
                status = 1
            else:
                print(f"{output.name} is current.")
            continue
        output.write_bytes(text.encode("utf-8"))
        print(f"Wrote {output.relative_to(ROOT).as_posix()}")
    return status


if __name__ == "__main__":
    sys.exit(main())
