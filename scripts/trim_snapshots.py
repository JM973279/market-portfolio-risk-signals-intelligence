"""Remove snapshot folders that current.json does not point to, in an image build context only.

    python3 scripts/trim_snapshots.py data/portfolio data/portfolio-kr

The deployed API reads only the snapshot that current.json points to; every earlier snapshot
stays in git history. Run this only on a throwaway checkout right before building images, so
each image carries one snapshot per market instead of every snapshot ever published (about
2 MB more per new US or Korean snapshot). Never commit its result.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def referenced(dataset):
    """Snapshot folder names that current.json (files and receipts) points to."""
    manifest = json.loads((Path(dataset) / "current.json").read_text(encoding="utf-8"))
    records = list(manifest["files"].values())
    records += list((manifest.get("collection") or {}).get("receipts", {}).values())
    names = set()
    for record in records:
        parts = Path(record["path"]).parts
        if len(parts) < 3 or parts[0] != "snapshots":
            raise ValueError(f"Unexpected snapshot path in {dataset}/current.json: {record['path']}")
        names.add(parts[1])
    return names


def trim(dataset):
    keep = referenced(dataset)
    folder = Path(dataset) / "snapshots"
    missing = [name for name in keep if not (folder / name).is_dir()]
    if missing:
        raise ValueError(f"{dataset}: current snapshot folder missing: {missing}")
    removed = [p for p in folder.iterdir() if p.is_dir() and p.name not in keep]
    for path in removed:
        shutil.rmtree(path)
    return sorted(keep), len(removed)


def main(argv=None):
    for dataset in (argv if argv is not None else sys.argv[1:]):
        keep, removed = trim(dataset)
        print(f"{dataset}: kept {', '.join(keep)}; removed {removed} older snapshot folders from the build context.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
