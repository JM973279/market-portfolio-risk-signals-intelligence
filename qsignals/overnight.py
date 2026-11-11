"""US-listed overnight prices aligned to the KRX session they precede.

A US session on date d closes at 05:00-06:00 KST on d+1, before the KRX open.
For KRX date t we therefore use the last stored US session strictly before t.
Nothing is filled: a missing close stays missing and the KRX date gets no value.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from qsignals.calendar import valid_date

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "data/input/overnight_us.csv"
DEFAULT_PROVENANCE = ROOT / "data/input/overnight_provenance.json"
# EWY: US-listed MSCI Korea ETF, i.e. Korean equities priced during US hours.
# ^SOX: PHLX Semiconductor index, the US semiconductor shock channel (README ①).
TICKERS = ("EWY", "^SOX")
# Longest normal gap between the US session and the next KRX session is a US
# holiday Monday (Friday -> Tuesday). Anything longer is treated as stale.
MAX_GAP_DAYS = 5


@dataclass(frozen=True)
class Overnight:
    krx_date: str
    us_date: str
    returns: dict


def read_overnight(path=DEFAULT_CSV, provenance_path=DEFAULT_PROVENANCE):
    """Return (rows, provenance) or (None, None) when nothing has been collected yet."""
    path, provenance_path = Path(path), Path(provenance_path)
    if not path.exists() or not provenance_path.exists():
        return None, None
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if hashlib.sha256(path.read_bytes()).hexdigest() != provenance.get("sha256"):
        raise ValueError("Overnight prices do not match provenance; rerun qsignals.overnight_refresh")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        tickers = tuple((reader.fieldnames or [])[1:])
        if not reader.fieldnames or reader.fieldnames[0] != "date" or not tickers:
            raise ValueError(f"Unexpected overnight columns: {reader.fieldnames}")
        if tickers != tuple(provenance.get("tickers", ())):
            raise ValueError("Overnight columns disagree with provenance tickers")
        rows, previous = [], ""
        for rec in reader:
            day = valid_date(rec["date"])
            if day <= previous:
                raise ValueError(f"Overnight dates must be unique and ascending: {previous} -> {day}")
            previous = day
            closes = {}
            for t in tickers:
                value = rec[t].strip()
                if value == "":
                    closes[t] = None
                    continue
                x = float(value)
                if not math.isfinite(x) or x <= 0:
                    raise ValueError(f"Invalid {t} close on {day}")
                closes[t] = x
            rows.append((day, closes))
    if len(rows) != provenance.get("rows") or (rows and rows[-1][0] != provenance.get("last_date")):
        raise ValueError("Overnight provenance row/date mismatch")
    return rows, provenance


def _complete_for(krx_date, rows, provenance):
    """True if every US session before krx_date had been collected.

    The collector records the next scheduled XNYS session after its last
    stored one; no US session exists strictly between them, so any KRX date up
    to and including that next session already has its preceding close.
    """
    return bool(rows) and (rows[-1][0] >= krx_date or provenance["next_us_session"] >= krx_date)


def align(krx_sessions, rows, provenance, tickers=None):
    """Map each KRX session to the close-to-close return of the preceding US session."""
    tickers = tuple(tickers or provenance["tickers"])
    days = [d for d, _ in rows]
    out = {}
    for krx in krx_sessions:
        i = bisect_left(days, krx) - 1  # last US date strictly before the KRX date
        if i < 1:
            continue
        us_date = days[i]
        if (date.fromisoformat(krx) - date.fromisoformat(us_date)).days > MAX_GAP_DAYS:
            continue
        if not _complete_for(krx, rows, provenance):
            continue
        now, before = rows[i][1], rows[i - 1][1]
        returns = {}
        for t in tickers:
            a, b = before.get(t), now.get(t)
            returns[t] = None if a is None or b is None else b / a - 1.0
        out[krx] = Overnight(krx, us_date, returns)
    return out
