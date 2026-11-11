"""Print the published last score date per market for commit messages.

Korea: data/input/provenance.json, US: data/input/us_provenance.json.
A missing file prints "none" for that market instead of failing the commit.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = {"korea": "data/input/provenance.json", "us": "data/input/us_provenance.json"}


def published_dates(root=ROOT):
    dates = {}
    for market, rel in FILES.items():
        path = Path(root) / rel
        dates[market] = json.loads(path.read_text(encoding="utf-8")).get("last_risk_date") if path.exists() else None
    return dates


def main(argv=None):
    root = Path(argv[0]) if argv else ROOT
    print(", ".join(f"{m} {d or 'none'}" for m, d in published_dates(root).items()))


if __name__ == "__main__":
    main(sys.argv[1:])
