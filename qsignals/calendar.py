"""Versioned KRX sessions, independent of rows that happened to be collected."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def valid_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(f"Invalid ISO date: {value!r}")
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError(f"Invalid ISO date: {value!r}")
    return value


@lru_cache(maxsize=1)
def load_sessions():
    path = ROOT / "data/calendar/xkrx_sessions.csv"
    meta = json.loads((path.parent / "provenance.json").read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
        raise ValueError("KRX calendar hash mismatch")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["date"]:
            raise ValueError("Unexpected KRX calendar schema")
        sessions = tuple(valid_date(r["date"]) for r in reader)
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ValueError("KRX calendar is empty, unordered or duplicated")
    return sessions


def require_coverage(first, last):
    meta = json.loads((ROOT / "data/calendar/provenance.json").read_text())
    if not meta["start"] <= first <= last <= meta["end"]:
        raise ValueError("Dates outside verified KRX calendar coverage; update the calendar explicitly")


def latest_closed_session(now=None, publication_lag_hours=0):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware current time required")
    local = now.astimezone(timezone(timedelta(hours=9)))
    require_coverage(local.date().isoformat(), local.date().isoformat())
    boundary = local - timedelta(hours=15 + publication_lag_hours, minutes=30)
    return max(day for day in load_sessions() if day <= boundary.date().isoformat())
