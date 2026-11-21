"""Run the frozen pipeline with a Korea collection-boundary adapter.

Only incomplete trailing equity sessions are excluded. Source receipts, expected
session, model, feature calculations and historical parity gates stay intact.
The upstream checkout and its hash-pinned files are never modified.
"""
from __future__ import annotations

import sys
from pathlib import Path

VERSION = "korea-trailing-observations-v1"
ANCHOR = "                equity = raw.loc[raw.KOSPI200.notna()]\n"


def complete_korea_history(equity, channels):
    """Reject internal gaps in *each* channel before selecting the common end."""
    ends = []
    for name in channels:
        end = equity[name].last_valid_index()
        if end is None or equity.loc[:end, name].isna().any():
            raise ValueError('Missing Korea equity-date channel; no imputation')
        ends.append(end)
    return equity.loc[:min(ends)].copy()


def adapted_source(source):
    # Fail closed if upstream changes this boundary; never bypass its existing gate.
    gate = ANCHOR + "                if equity[channels].isna().any().any():\n"
    if source.count(gate) != 1:
        raise ValueError("Unsupported frozen Korea collection boundary")
    return source.replace(ANCHOR, ANCHOR + "                equity = _complete_korea_history(equity, channels)\n", 1)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    runner = Path(args.pop(0)).resolve()
    source = adapted_source(runner.read_text(encoding="utf-8"))
    # Match direct script execution; otherwise qsignals/calendar.py shadows
    # the standard-library calendar module during pandas imports.
    sys.path[0] = str(runner.parent)
    sys.argv = [str(runner), *args]
    namespace = {"__name__": "__main__", "__file__": str(runner),
                 "_complete_korea_history": complete_korea_history}
    exec(compile(source, str(runner), "exec"), namespace)


if __name__ == "__main__":
    main()
