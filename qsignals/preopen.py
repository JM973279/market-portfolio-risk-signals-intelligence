"""Pre-open news log: classifications recorded before the KRX open.

A row may only be written between the previous KRX close (15:30 KST) and
08:30 KST on the session it describes. Hindsight backfills are therefore
rejected by construction, and an LLM classifier cannot use knowledge of the
outcome. The log is evaluated only after the pre-registered minimum history.
"""

from __future__ import annotations

import csv
import re
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from qsignals.calendar import load_sessions, require_coverage, valid_date
from qsignals.events import SOURCE_QUALITY, TRIGGERS

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "data/events/preopen_log.csv"
KST = timezone(timedelta(hours=9))
CSV_FIELDS = ("krx_date", "recorded_at", "category", "stance", "summary", "source_urls", "source_quality", "classifier")
CATEGORIES = {**TRIGGERS, "none": "특이 뉴스 없음"}
STANCES = {"risk_off": "위험 회피", "neutral": "중립", "risk_on": "위험 선호"}
CLASSIFIER_RE = re.compile(r"^(manual|rule:[a-z0-9._-]+|llm:[A-Za-z0-9._-]+)$")
OPEN_CUTOFF = (8, 30)
CLOSE = (15, 30)
# Pre-registered evaluation gate: at least one year of logged sessions and
# enough next-session drops to estimate precision at all.
MIN_LOGGED_SESSIONS = 250
MIN_DROP_SESSIONS = 10
DROP_PCT = -2.0
MAX_FLAGS_PER_YEAR = 5


def _window(krx_date, sessions):
    pos = bisect_left(sessions, krx_date)
    if pos == 0 or pos == len(sessions) or sessions[pos] != krx_date:
        raise ValueError(f"Not a KRX session with a previous session: {krx_date}")
    prev = datetime.fromisoformat(sessions[pos - 1]).replace(hour=CLOSE[0], minute=CLOSE[1], tzinfo=KST)
    cutoff = datetime.fromisoformat(krx_date).replace(hour=OPEN_CUTOFF[0], minute=OPEN_CUTOFF[1], tzinfo=KST)
    return prev, cutoff


def parse_row(rec, sessions=None):
    sessions = sessions or load_sessions()
    rec = {k: (v or "").strip() for k, v in rec.items()}
    where = f"{rec['krx_date']}/{rec['classifier']}"
    valid_date(rec["krx_date"])
    require_coverage(rec["krx_date"], rec["krx_date"])
    recorded = datetime.fromisoformat(rec["recorded_at"])
    if recorded.tzinfo is None:
        raise ValueError(f"{where}: recorded_at needs a UTC offset")
    start, cutoff = _window(rec["krx_date"], sessions)
    if not start <= recorded < cutoff:
        raise ValueError(f"{where}: recorded outside the pre-open window ({start.isoformat()} ~ {cutoff.isoformat()})")
    if rec["category"] not in CATEGORIES:
        raise ValueError(f"{where}: unknown category {rec['category']!r}")
    if rec["stance"] not in STANCES:
        raise ValueError(f"{where}: unknown stance {rec['stance']!r}")
    if not rec["summary"]:
        raise ValueError(f"{where}: missing summary")
    urls = tuple(u.strip() for u in rec["source_urls"].split(";") if u.strip())
    if any(urlsplit(u).scheme != "https" or not urlsplit(u).hostname for u in urls):
        raise ValueError(f"{where}: source URLs must be https")
    if rec["source_quality"] not in SOURCE_QUALITY or (rec["source_quality"] == "unsourced") != (not urls):
        raise ValueError(f"{where}: source_quality and source_urls disagree")
    if not CLASSIFIER_RE.match(rec["classifier"]):
        raise ValueError(f"{where}: classifier must be manual, rule:<version> or llm:<model>")
    return {**rec, "source_urls": urls}


def read_log(path=DEFAULT_LOG):
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise ValueError(f"Unexpected pre-open log columns: {reader.fieldnames}")
        rows = [parse_row(rec) for rec in reader]
    keys = [(r["krx_date"], r["classifier"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate krx_date/classifier in pre-open log")
    return sorted(rows, key=lambda r: (r["krx_date"], r["classifier"]))


def readiness(log, rows):
    """Per-classifier progress toward the evaluation gate; no scoring before it."""
    by_date = {r.date: r for r in rows}
    sessions = load_sessions()
    out = {}
    for name in sorted({r["classifier"] for r in log}):
        entries = [r for r in log if r["classifier"] == name]
        drops = flags = 0
        outcomes = []
        for e in entries:
            pos = bisect_left(sessions, e["krx_date"])
            now, prev = by_date.get(e["krx_date"]), by_date.get(sessions[pos - 1])
            if now and prev and now.kospi200_close and prev.kospi200_close:
                ret = (now.kospi200_close / prev.kospi200_close - 1) * 100
                outcomes.append((e["stance"] == "risk_off", ret <= DROP_PCT))
        drops = sum(d for _, d in outcomes)
        flags = sum(f for f, _ in outcomes)
        ready = len(outcomes) >= MIN_LOGGED_SESSIONS and drops >= MIN_DROP_SESSIONS
        entry = {"logged": len(entries), "with_outcome": len(outcomes), "drops": drops, "ready": ready}
        if ready:
            years = len(outcomes) / 250
            hits = sum(f and d for f, d in outcomes)
            entry.update({"flags_per_year": flags / years, "precision": hits / flags if flags else None,
                          "base_rate": drops / len(outcomes), "recall": hits / drops})
        out[name] = entry
    return out
