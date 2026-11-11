"""Write frontend/public/data/operational-markets.json from this repo's data.

    python3 -m qsignals.export_frontend [--check]

The copied frontend (frontend/, from the deployed repo) reads three JSON files.
Only the operational one changes with this repo's refreshes, so only it is
generated here:

- operational-markets.json: built from data/input/operational/{korea,us}.json
  (each market's latest verified pipeline block, saved by qsignals.refresh).
  Every score in a block is checked against data/input/{market}_scores.csv;
  a mismatch stops the export.
- global-markets.json, korea-monitor.json: frozen research exports copied with
  the frontend (walk-forward OOS, breadth monitor). They are not refreshed.

The two markets can come from different refresh runs; runId lists both.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qsignals.scores import MARKETS, read_scores

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT = PROJECT_ROOT / "data/input"
OUTPUT = PROJECT_ROOT / "frontend/public/data/operational-markets.json"
POST_CUTOFF = ("RETROSPECTIVE_INFERENCE", "OPERATIONAL")


def check_block(market, block, rows):
    """Every scored block date must match the CSV; every post-cutoff CSV row must be in the block."""
    by_date = {r.date: r for r in rows}
    history = {p["date"]: p for p in block.get("history", [])}
    for date, point in history.items():
        row = by_date.get(date)
        if row is None:
            raise ValueError(f"{market}: {date} is in the status block but not in {market}_scores.csv")
        if row.record_type in POST_CUTOFF and (row.risk_v1, row.msi, row.stress_threshold) != (
                point.get("risk"), point.get("msi"), point.get("threshold")):
            raise ValueError(f"{market}: {date} differs between the status block and {market}_scores.csv")
    missing = [r.date for r in rows if r.record_type in POST_CUTOFF and r.date not in history]
    if missing:
        raise ValueError(f"{market}: {len(missing)} CSV rows are missing from the status block (first {missing[0]})")


def build(input_dir=INPUT):
    saved = {}
    for market in MARKETS:
        path = Path(input_dir) / "operational" / f"{market}.json"
        if not path.exists():
            raise FileNotFoundError(f"{path} missing: run python3 -m qsignals.refresh first")
        saved[market] = json.loads(path.read_text(encoding="utf-8"))
        check_block(market, saved[market]["block"], read_scores(Path(input_dir) / f"{market}_scores.csv", market))
    return {
        "schema_version": 1,
        "runId": " + ".join(f"{m}:{saved[m]['runId']}" for m in MARKETS),
        "generatedAt": max(saved[m]["generatedAt"] for m in MARKETS),
        "mode": "qualitative-signals-import",
        "markets": {m: saved[m]["block"] for m in MARKETS},
        "sourceValuesIncluded": False,
    }


def render(export):
    return json.dumps(export, indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if the frontend export is stale")
    args = parser.parse_args(argv)
    text = render(build())
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT.relative_to(PROJECT_ROOT)} is stale; run python3 -m qsignals.export_frontend", file=sys.stderr)
            return 1
        print(f"{OUTPUT.relative_to(PROJECT_ROOT)} is current.")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
