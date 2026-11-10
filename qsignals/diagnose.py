"""Run the event diagnostics and write reports/.

    python3 -m qsignals.diagnose
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from qsignals.diagnostics import VERDICTS, diagnose_all
from qsignals.events import read_events
from qsignals.report import render_markdown, write_csv
from qsignals.scores import read_scores

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, default=PROJECT_ROOT / "data/input/korea_scores.csv")
    parser.add_argument("--provenance", type=Path, default=PROJECT_ROOT / "data/input/provenance.json")
    parser.add_argument("--events", type=Path, default=PROJECT_ROOT / "data/events/kospi_2026_events.csv")
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "reports")
    parser.add_argument("--scan-start", default="2026-01-01")
    args = parser.parse_args(argv)

    rows = read_scores(args.scores)
    events = read_events(args.events)
    provenance = json.loads(args.provenance.read_text(encoding="utf-8"))

    diagnoses = diagnose_all(events, rows)
    write_csv(diagnoses, args.out_dir / "event_diagnostics.csv")
    md = render_markdown(events, diagnoses, rows, provenance, args.scan_start)
    (args.out_dir / "event_diagnostics.md").write_text(md, encoding="utf-8")

    counts = Counter(d.verdict for d in diagnoses)
    print(f"{len(diagnoses)} events: " + ", ".join(f"{VERDICTS[k]} {v}" for k, v in counts.items()))
    print(f"wrote {args.out_dir / 'event_diagnostics.md'}")


if __name__ == "__main__":
    main()
