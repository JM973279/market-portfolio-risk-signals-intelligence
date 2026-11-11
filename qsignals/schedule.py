"""Scheduled US releases mapped to the first KRX session that can react.

Display only. These dates are never model inputs: a scheduled date says when
risk is concentrated, not what the outcome will be, and the 2016-2025 pilot
found no measurable accuracy gain (README, 예정 이벤트 일정표).
"""

from __future__ import annotations

import csv
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from qsignals.calendar import load_sessions, require_coverage, valid_date

EVENT_TYPES = {
    "FOMC": "FOMC 결정",
    "CPI": "미국 CPI",
    "NFP": "미국 고용보고서",
    "ELECTION": "미국 선거",
}
CSV_FIELDS = ("event_id", "us_date", "event_type", "description", "release_time_et", "source_url", "verified_at")
# A KOSPI sell-off on KRX day t is shown next to releases whose first KRX
# session falls on t-2..t. Fixed before looking at any outcome.
NEARBY_SESSIONS = 2


@dataclass(frozen=True)
class Scheduled:
    event_id: str
    us_date: str
    event_type: str
    description: str
    release_time_et: str
    source_url: str
    verified_at: str
    krx_session: str


def first_krx_session_after(us_date, sessions=None):
    """US releases land after the KRX close (US day runs overnight in Seoul)."""
    sessions = sessions or load_sessions()
    i = bisect_right(sessions, us_date)
    if i == len(sessions):
        raise ValueError(f"No KRX session after {us_date}; update the calendar explicitly")
    return sessions[i]


def read_schedule(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise ValueError(f"Unexpected schedule columns: {reader.fieldnames}")
        records = list(reader)
    out, seen = [], set()
    for rec in records:
        rec = {k: v.strip() for k, v in rec.items()}
        where = rec["event_id"] or "<missing id>"
        if not rec["event_id"] or rec["event_id"] in seen:
            raise ValueError(f"{where}: missing or duplicate event_id")
        seen.add(rec["event_id"])
        valid_date(rec["us_date"])
        valid_date(rec["verified_at"])
        if rec["event_type"] not in EVENT_TYPES:
            raise ValueError(f"{where}: unknown event_type {rec['event_type']!r}")
        if not rec["description"]:
            raise ValueError(f"{where}: missing description")
        if rec["release_time_et"] and not (len(rec["release_time_et"]) == 5 and rec["release_time_et"][2] == ":"):
            raise ValueError(f"{where}: release_time_et must be HH:MM")
        url = urlsplit(rec["source_url"])
        if url.scheme != "https" or not url.hostname:
            raise ValueError(f"{where}: source_url must be https")
        require_coverage(rec["us_date"], rec["us_date"])
        out.append(Scheduled(**rec, krx_session=first_krx_session_after(rec["us_date"])))
    return sorted(out, key=lambda s: (s.us_date, s.event_id))


def nearby(schedule, krx_date, sessions=None, window=NEARBY_SESSIONS):
    """Releases whose first reacting KRX session is within window sessions up to krx_date."""
    sessions = sessions or load_sessions()
    pos = bisect_left(sessions, krx_date)
    if pos == len(sessions) or sessions[pos] != krx_date:
        raise ValueError(f"Not a KRX session: {krx_date}")
    first = sessions[max(0, pos - window)]
    return [s for s in schedule if first <= s.krx_session <= krx_date]


def upcoming(schedule, after_session, count=5, sessions=None):
    """Releases reacting in the next `count` KRX sessions after `after_session`."""
    sessions = sessions or load_sessions()
    pos = bisect_right(sessions, after_session)
    window = sessions[pos:pos + count]
    if not window:
        return []
    return [s for s in schedule if window[0] <= s.krx_session <= window[-1]]
