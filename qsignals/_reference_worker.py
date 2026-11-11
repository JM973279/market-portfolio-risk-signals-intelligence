"""Rebuild and verify the Korea V1 reference matrix (runs under the inference Python).

    <inference-python> qsignals/_reference_worker.py --v1-tree DIR --mpri-tree DIR \
        --raw-dir DIR --end YYYY-MM-DD --out-dir DIR

The frozen pipeline checks new Korea features against
data/processed/early_warning_v2/korea_feature_matrix_v1_reproduction.csv, a
gitignored file that exists only where it was first built. This rebuilds it
with the same code (V1 MSI/target builders at the contract commit, the deployed
repo's build_korea_features_v2.py) from raw history truncated to --end, then
checks it against evidence committed in the deployed repo:

- Korea_MSI and Stress_Threshold equal global-markets.json on every shared date;
- the frozen model on the rebuilt features reproduces every risk score in the
  committed operational-markets.json history.

Writes the matrix and verification.json to --out-dir; exits 1 if a check fails.
The rebuilt file is not byte-identical to the original (its SHA-256 differs),
so verification.json records both hashes.
"""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import sys
from pathlib import Path

# Direct execution adds qsignals/ to sys.path, which would shadow the stdlib
# calendar module with qsignals/calendar.py during pandas imports.
if __package__ in (None, ""):
    script_dir = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if Path(p).resolve() != script_dir]

import joblib
import numpy as np
import pandas as pd

RAW = ("krx_indices.csv", "vkospi.csv", "ecos_credit.csv")
MATRIX = "korea_feature_matrix_v1_reproduction.csv"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(v1, mpri, raw, stage, inference_only):
    """Run the V1 MSI/target builders and the deployed feature builder on `raw`."""
    stage.mkdir(parents=True)
    paths = {n: str(raw / n) for n in RAW}
    with contextlib.redirect_stdout(io.StringIO()):
        msi = load(v1 / "src/korea/build_korea_stress_index.py", f"msi_{stage.name}")
        msi.KRX_PATH, msi.VKOSPI_PATH, msi.CREDIT_PATH = paths["krx_indices.csv"], paths["vkospi.csv"], paths["ecos_credit.csv"]
        msi.OUTPUT_PATH = str(stage / "korea_stress_index.csv")
        msi.main()
        target = load(v1 / "src/korea/build_korea_target.py", f"target_{stage.name}")
        target.INPUT_PATH, target.OUTPUT_PATH = msi.OUTPUT_PATH, str(stage / "korea_targets.csv")
        target.main()
        features = load(mpri / "market_engine/early_warning_v2/build_korea_features_v2.py", f"features_{stage.name}")
        features.KRX_PATH, features.VKOSPI_PATH, features.CREDIT_PATH = msi.KRX_PATH, msi.VKOSPI_PATH, msi.CREDIT_PATH
        features.TARGET_PATH = target.OUTPUT_PATH
        features.OUTPUT_PATH = str(stage / MATRIX)
        features.LATEST_OUTPUT_PATH = str(stage / "latest_features.csv")
        features.main(inference_only=inference_only)
    return stage


def main():
    parser = argparse.ArgumentParser()
    for name in ("--v1-tree", "--mpri-tree", "--raw-dir", "--out-dir"):
        parser.add_argument(name, type=Path, required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()

    contract = json.loads((args.mpri_tree / "market_engine/operations/contract.json").read_text())["markets"]["korea"]
    work = args.out_dir / "build"
    shutil.rmtree(work, ignore_errors=True)
    truncated = work / "raw"
    truncated.mkdir(parents=True)
    end = pd.Timestamp(args.end)
    for name in RAW:
        frame = pd.read_csv(args.raw_dir / name, dtype=str)
        frame[pd.to_datetime(frame["Date"]) <= end].to_csv(truncated / name, index=False)

    research = build(args.v1_tree, args.mpri_tree, truncated, work / "research", inference_only=False)
    latest = build(args.v1_tree, args.mpri_tree, args.raw_dir, work / "latest", inference_only=True)

    checks = {}
    stress = pd.read_csv(research / "korea_stress_index.csv", index_col="Date", parse_dates=True)
    research_json = json.loads((args.mpri_tree / "frontend/public/data/global-markets.json").read_text())
    recorded = pd.DataFrame(research_json["korea"]).set_index("date")
    recorded.index = pd.to_datetime(recorded.index)
    for ours, theirs in (("Korea_MSI", "msi"), ("Stress_Threshold", "threshold")):
        pair = pd.concat([stress[ours], recorded[theirs]], axis=1, join="inner").dropna()
        diff = float((pair.iloc[:, 0] - pair.iloc[:, 1]).abs().max())
        checks[f"{ours}_vs_global_markets"] = {"dates": len(pair), "max_abs_diff": diff, "passed": len(pair) > 1000 and diff <= 1e-9}

    model_path = args.mpri_tree / contract["model"]
    if sha256(model_path) != contract["model_sha256"]:
        raise SystemExit("Frozen model hash mismatch")
    model = joblib.load(model_path)
    history = pd.DataFrame(json.loads((args.mpri_tree / "frontend/public/data/operational-markets.json").read_text())["markets"]["korea"]["history"])
    history = history.set_index(pd.to_datetime(history["date"]))
    features = pd.read_csv(latest / "latest_features.csv", index_col="Date", parse_dates=True)
    days = features.index.intersection(history.index)
    risk = model.predict_proba(features.loc[days, contract["features"]])[:, 1] if len(days) else np.array([])
    diff = float(np.abs(risk - history.loc[days, "risk"].to_numpy()).max()) if len(days) else None
    checks["frozen_model_vs_committed_history"] = {
        "dates": len(days),
        "first": days.min().strftime("%Y-%m-%d") if len(days) else None,
        "last": days.max().strftime("%Y-%m-%d") if len(days) else None,
        "max_abs_diff": diff,
        "passed": len(days) >= 10 and diff is not None and diff <= 1e-12,
    }

    matrix = research / MATRIX
    labeled = int(pd.read_csv(matrix, usecols=["Target_10D"])["Target_10D"].notna().sum())
    passed = all(c["passed"] for c in checks.values())
    shutil.copy2(matrix, args.out_dir / MATRIX)
    report = {
        "passed": passed,
        "end": args.end,
        "contract_reference_sha256": contract["reference_sha256"],
        "rebuilt_sha256": sha256(args.out_dir / MATRIX),
        "byte_identical": sha256(args.out_dir / MATRIX) == contract["reference_sha256"],
        "rows": int(len(pd.read_csv(matrix, usecols=["Date"]))),
        "labeled_target_10d_rows": labeled,
        "checks": checks,
    }
    (args.out_dir / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
