"""Copy the Korea V1 score series out of the deployed repo (read-only).

    python3 -m qsignals.import_scores [--source-root PATH]

Reads frontend/public/data/{global-markets,operational-markets}.json from the
deployed project, writes data/input/korea_scores.csv and records SHA-256,
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

from qsignals.scores import build_rows, write_scores

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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data" / "input")
    args = parser.parse_args(argv)

    source_root = args.source_root.resolve()
    payloads, files = {}, {}
    for key, rel in SOURCE_FILES.items():
        raw = (source_root / rel).read_bytes()
        payloads[key] = json.loads(raw)
        files[key] = {
            "path": rel,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    rows = build_rows(payloads["global_markets"], payloads["operational_markets"])
    write_scores(rows, args.output_dir / "korea_scores.csv")

    korea_ops = payloads["operational_markets"]["markets"]["korea"]
    scored = [r for r in rows if r.risk_v1 is not None]
    priced = [r for r in rows if r.kospi200_close is not None]
    dirty = _git(source_root, "status", "--porcelain", "--", *SOURCE_FILES.values())

    provenance = {
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_repo": source_root.name,
        "source_git_branch": _git(source_root, "branch", "--show-current"),
        "source_git_commit": _git(source_root, "rev-parse", "HEAD"),
        "source_files_modified_locally": bool(dirty) if dirty is not None else None,
        "files": files,
        "operational_run_id": payloads["operational_markets"].get("runId"),
        "operational_model_sha256": korea_ops.get("modelSha256"),
        "training_cutoff": korea_ops.get("trainingCutoff"),
        "rows": len(rows),
        "record_type_counts": dict(sorted(Counter(r.record_type for r in rows).items())),
        "first_date": rows[0].date,
        "last_date": rows[-1].date,
        "last_risk_date": scored[-1].date,
        "last_price_date": priced[-1].date,
    }
    out = args.output_dir / "provenance.json"
    out.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(provenance, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
