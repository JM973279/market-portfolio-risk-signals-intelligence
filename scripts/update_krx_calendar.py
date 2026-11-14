"""Keep the versioned KRX session calendar (data/calendar/xkrx_sessions.csv) ahead of today.

    python3 scripts/update_krx_calendar.py --check                  # committed file == library rebuild
    python3 scripts/update_krx_calendar.py --extend-within-days 90  # extend to next year-end when due

Every Korea batch refuses dates outside the calendar's coverage (qsignals.calendar), so the
coverage must be extended before it ends. Sessions are the pinned exchange_calendars XKRX
sessions minus provenance `additional_closures` (closures the library does not know, such as
election days). KRX announces the next year's closures in December and ad hoc closures at short
notice: add those to `additional_closures` and run this again. Needs requirements.portfolio-refresh.txt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CALENDAR = ROOT / "data/calendar/xkrx_sessions.csv"
PROVENANCE = ROOT / "data/calendar/provenance.json"


def library_sessions(start, end):
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XKRX", start=start, end=end)
    return [day.strftime("%Y-%m-%d") for day in cal.sessions_in_range(start, end)], xcals.__version__


def render(sessions):
    return ("date\n" + "".join(f"{day}\n" for day in sessions)).encode()


def build(start, end, closures, sessions_source=library_sessions):
    sessions, version = sessions_source(start, end)
    return render([day for day in sessions if day not in closures]), version


def extension_end(meta, today, within_days):
    """Next year-end once coverage ends within `within_days` of today, else None."""
    end = date.fromisoformat(meta["end"])
    if end - today > timedelta(days=within_days):
        return None
    return f"{max(end.year, today.year) + 1}-12-31"


def main(argv=None, today=None, sessions_source=library_sessions):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail unless the committed file matches the library rebuild")
    mode.add_argument("--extend-within-days", type=int, help="extend to the next year-end when coverage ends this soon")
    args = parser.parse_args(argv)
    meta = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    closures = set(meta.get("additional_closures", {}))
    if args.check:
        rebuilt, version = build(meta["start"], meta["end"], closures, sessions_source)
        if rebuilt != CALENDAR.read_bytes():
            print(f"::error::{CALENDAR.name} does not match exchange_calendars {version} XKRX "
                  "minus additional_closures; fix it before extending.", file=sys.stderr)
            return 1
        print(f"Calendar matches exchange_calendars {version} through {meta['end']}.")
        return 0
    today = today or datetime.now(timezone(timedelta(hours=9))).date()
    end = extension_end(meta, today, args.extend_within_days)
    if end is None:
        print(f"Calendar covers through {meta['end']}; no extension due.")
        return 0
    data, version = build(meta["start"], end, closures, sessions_source)
    if not data.startswith(CALENDAR.read_bytes()):
        print("::error::Rebuilt calendar changes already-published sessions; not extending.", file=sys.stderr)
        return 1
    CALENDAR.write_bytes(data)
    meta.update(end=end, library_version=version, sha256=hashlib.sha256(data).hexdigest())
    PROVENANCE.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"::warning::KRX calendar extended to {end} from exchange_calendars {version}. Check KRX's closure "
          "notice for the new year (published in December) and add any missing closure to additional_closures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
