"""Copy the Korea and US V1 score series out of the deployed repo (read-only).

    python3 -m qsignals.import_scores [--source-root PATH]

Reads frontend/public/data/{global-markets,operational-markets}.json from the
deployed project, writes data/input/{korea,us}_scores.csv and records SHA-256,
source commit and row counts in data/input/provenance.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from qsignals.scores import MARKETS, build_rows, read_scores, write_scores

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT.parent / "market-portfolio-risk-intelligence"
SOURCE_FILES = {
    "global_markets": "frontend/public/data/global-markets.json",
    "operational_markets": "frontend/public/data/operational-markets.json",
}


def _git(source_root, *args):
    try:
        out = subprocess.run(
            ["git", "-C", str(source_root), *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def _summary(rows):
    scored = [r for r in rows if r.risk_v1 is not None]
    priced = [r for r in rows if r.kospi200_close is not None]
    return {
        "rows": len(rows),
        "record_type_counts": dict(sorted(Counter(r.record_type for r in rows).items())),
        "first_date": rows[0].date,
        "last_date": rows[-1].date,
        "last_risk_date": scored[-1].date,
        "last_price_date": priced[-1].date if priced else None,
    }


SOURCE_KEYS = ("imported_at", "source_repo", "source_git_branch", "source_git_ref", "source_git_commit",
               "source_files_modified_locally", "files", "operational_run_id")
SUMMARY_KEYS = ("operational_model_sha256", "training_cutoff", "rows", "record_type_counts",
                "first_date", "last_date", "last_risk_date", "last_price_date")


def import_scores(source_root, output_dir, extra_provenance=None, markets=MARKETS):
    """Write {market}_scores.csv and provenance.json from a deployed-repo tree.

    `extra_provenance` overrides/extends the recorded fields (used by
    qsignals.refresh, whose source tree is a git archive without .git); its
    `source_*` keys describe where this import's files came from.
    `markets` limits which score files are rewritten. A market left out keeps
    its previous file and its previous source record, so every entry in
    `markets` names the commit and export its own CSV was built from. The
    top-level source/count fields always describe korea_scores.csv, the input
    of the event diagnostics.
    """
    source_root = Path(source_root).resolve()
    output_dir = Path(output_dir)
    if not markets:
        raise ValueError("No market to import")
    payloads, files = {}, {}
    for key, rel in SOURCE_FILES.items():
        raw = (source_root / rel).read_bytes()
        payloads[key] = json.loads(raw)
        files[key] = {
            "path": rel,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    extra = dict(extra_provenance or {})
    dirty = _git(source_root, "status", "--porcelain", "--", *SOURCE_FILES.values())
    source = {
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_repo": source_root.name,
        "source_git_branch": _git(source_root, "branch", "--show-current"),
        "source_git_ref": None,
        "source_git_commit": _git(source_root, "rev-parse", "HEAD"),
        "source_files_modified_locally": bool(dirty) if dirty is not None else None,
        "files": files,
        "operational_run_id": payloads["operational_markets"].get("runId"),
    }
    source.update({k: extra.pop(k) for k in list(extra) if k in SOURCE_KEYS})

    previous_path = output_dir / "provenance.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    summaries = {}
    for market in markets:
        rows = build_rows(payloads["global_markets"], payloads["operational_markets"], market)
        write_scores(rows, output_dir / f"{market}_scores.csv", market)
        ops = payloads["operational_markets"]["markets"][market]
        summaries[market] = {"file": f"{market}_scores.csv", **source, "operational_model_sha256": ops.get("modelSha256"),
                             "training_cutoff": ops.get("trainingCutoff"), **_summary(rows)}
    for market in MARKETS:
        kept = output_dir / f"{market}_scores.csv"
        if market in summaries or not kept.exists():
            continue
        # Older provenance (Korea only) kept these fields at the top level.
        before = previous.get("markets", {}).get(market) or (previous if market == "korea" else {})
        summaries[market] = {"file": kept.name, **{k: before.get(k) for k in SOURCE_KEYS},
                             **{k: before.get(k) for k in SUMMARY_KEYS[:2]}, **_summary(read_scores(kept, market)),
                             "kept_from_previous_import": True}
    if "korea" not in summaries:
        raise ValueError("Korea scores missing: import Korea at least once")
    korea = summaries["korea"]

    provenance = {
        **{k: korea[k] for k in SOURCE_KEYS},
        **{k: korea[k] for k in SUMMARY_KEYS},
        "markets": summaries,
    }
    provenance.update(extra)
    out = output_dir / "provenance.json"
    out.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data" / "input")
    args = parser.parse_args(argv)
    provenance = import_scores(args.source_root, args.output_dir)
    print(json.dumps(provenance, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
