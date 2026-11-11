"""Read-only presentation snapshot. Never runs a model or writes research inputs.

Original V1 remains a separate project. Only explicitly identified stored columns
are copied; missing dates/values are never filled. Run manually, then rebuild.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_source(path, columns, registry, key, project):
    raw = path.read_bytes()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not set(columns + ["Date"]).issubset(reader.fieldnames or []):
            raise ValueError(f"{key}: required columns absent")
        rows = list(reader)
    dates = [row["Date"] for row in rows]
    if len(dates) != len(set(dates)) or dates != sorted(dates):
        raise ValueError(f"{key}: non-unique or unsorted dates")
    from datetime import date
    for value in dates:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError(f"{key}: non-daily date")
    for row in rows:
        for column in columns:
            value = row[column]
            row[column] = None if value in ("", "nan", "NaN") else float(value)
            number = row[column]
            if number is not None and not math.isfinite(number):
                raise ValueError(f"{key}: non-finite value")
            if column == "Prob_XGBoost" and number is not None and not 0 <= number <= 1:
                raise ValueError(f"{key}: invalid probability units")
    registry[key] = {"project": project, "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else f"{path.parents[2].name}/{'/'.join(path.parts[-3:])}", "rows": len(rows), "first": dates[0] if dates else None, "latest": dates[-1] if dates else None, "sha256": hashlib.sha256(raw).hexdigest()}
    return rows


def prepare(original):
    sources, issues = {}, []
    monitor = json.loads((ROOT / "frontend/public/data/korea-monitor.json").read_text())
    korea = read_source(ROOT / "data/processed/early_warning_v2/korea_feature_matrix_v1_reproduction.csv", ["KOSPI200"], sources, "korea_index", "Current project · frozen V1 reproduction")
    korea_index = {row["Date"]: row["KOSPI200"] for row in korea}
    kr = [{"date": row["Date"], "price": korea_index.get(row["Date"]), "risk": row["Prob_XGBoost"], "msi": row["Korea_MSI"], "threshold": row["Stress_Threshold"]} for row in monitor["history"]]
    us = []
    metrics = []
    try:
        predictions = read_source(original / "data/processed/oos_predictions_10d.csv", ["SPY", "MSI", "Prob_XGBoost"], sources, "us_oos", "Original V1 · separate completed project")
        features = read_source(original / "data/features/feature_matrix.csv", ["SPY", "MSI", "Stress_Threshold", "Is_Stress_Event"], sources, "us_features", "Original V1 · separate completed project")
        pred = {row["Date"]: row for row in predictions}
        feature = {row["Date"]: row for row in features}
        # OOS overlapping SPY/MSI values must agree with the documented feature source.
        for row in predictions:
            other = feature.get(row["Date"])
            if other is None or any(not math.isclose(row[c], other[c], rel_tol=1e-9, abs_tol=1e-9) for c in ["SPY", "MSI"]):
                raise ValueError("US OOS and feature source disagree")
        start = predictions[0]["Date"]
        for day in sorted(set(pred) | set(feature)):
            if day < start:
                continue
            f, p = feature.get(day, {}), pred.get(day, {})
            us.append({"date": day, "price": f.get("SPY"), "msi": f.get("MSI"), "threshold": f.get("Stress_Threshold"), "risk": p.get("Prob_XGBoost"), "stress": f.get("Is_Stress_Event")})
        metric_path = original / "data/processed/multi_horizon_metrics.csv"
        with metric_path.open(encoding="utf-8-sig") as handle:
            saved = list(csv.DictReader(handle))
        sources["us_validation"] = {"project": "Original V1 · separate completed project", "path": "market-stress-early-warning/data/processed/multi_horizon_metrics.csv", "rows": len(saved), "first": None, "latest": None, "sha256": hashlib.sha256(metric_path.read_bytes()).hexdigest()}
        for row in saved:
            if row["Model"] != "XGBoost":
                continue
            horizon = row["Horizon"].lower()
            verification = read_source(original / f"data/processed/oos_predictions_{horizon}.csv", ["Prob_XGBoost"], sources, f"us_{horizon}_validation", "Original V1 · separate completed project")
            if int(row["OOS_Observations"]) != len(verification) or row["OOS_Start"] != verification[0]["Date"] or row["OOS_End"] != verification[-1]["Date"]:
                raise ValueError("Stored validation period/count mismatch")
            metrics.append({"horizon": row["Horizon"], "auc": float(row["ROC_AUC"]), "precision": float(row["Precision_0.5"]), "recall": float(row["Recall_0.5"]), "f1": float(row["F1_0.5"]), "start": row["OOS_Start"], "end": row["OOS_End"], "n": int(row["OOS_Observations"])})
    except (OSError, ValueError, KeyError) as error:
        us, metrics = [], []
        issues.append(f"Original V1 US snapshot unavailable: {error}")
    pairs = ["corr_KOSPI200_SPY", "corr_KOSPI200_TLT", "corr_KOSPI200_GLD", "corr_SPY_TLT", "corr_SPY_GLD", "corr_TLT_GLD"]
    corr = read_source(ROOT / "data/processed/signal_divergence/cross_asset_signal.csv", pairs, sources, "correlation_pairs", "Current project · Korea confirmation only")
    correlation = [{"date": row["Date"], "values": [row[p] for p in pairs]} for row in corr if any(row[p] is not None for p in pairs)]
    return {"schema_version": 1, "asOf": monitor["latest"]["Date"] if monitor["latest"] else None, "us": us, "korea": kr, "usMetrics": metrics, "correlation": correlation, "sources": sources, "issues": issues}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-v1-root", type=Path, default=ROOT.parent / "market-stress-early-warning")
    args = parser.parse_args()
    result = prepare(args.original_v1_root)
    output = ROOT / "frontend/public/data/global-markets.json"
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    print(f"Presentation snapshot: {len(result['us'])} US / {len(result['korea'])} Korea observations; {len(result['usMetrics'])} stored validation rows")
    for issue in result["issues"]:
        print(issue)
