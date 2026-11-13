"""Actions-only collection of US overnight prices (EWY, ^SOX).

    /tmp/collector/bin/python -m qsignals.overnight_refresh

Runs in the isolated collection venv (requirements.portfolio-refresh.txt), like
the portfolio refresh. The web, reports and tests read only the stored CSV.
Every completed XNYS session becomes a row; a missing provider close stays
blank and is never filled from another day.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from qsignals.deferral import deferral, warn
from qsignals.overnight import DEFAULT_CSV, DEFAULT_PROVENANCE, TICKERS
from qsignals.portfolio_data import PortfolioError
from qsignals.portfolio_refresh import completed_sessions, fetch_quotes

START = "2016-01-04"
# Allow isolated provider gaps (recorded, never filled) but not a broken feed.
MIN_COVERAGE = 0.99


def next_session_after(day):
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS", start=day, end=f"{int(day[:4]) + 1}-12-31")
    later = [d.strftime("%Y-%m-%d") for d in cal.sessions if d.strftime("%Y-%m-%d") > day]
    if not later:
        raise PortfolioError("다음 미국 거래일을 찾지 못했습니다.", "invalid_data")
    return later[0]


def build(sessions, quotes, next_session, tickers=TICKERS):
    """Pure validation: one row per completed session, blanks for provider gaps.

    A missing close on the newest session blocks publication as 'provider_delayed' (Yahoo is
    late with it or withholding a stored one); main() keeps the stored data and retries while
    it is within qsignals.deferral's limit.
    """
    if sessions != sorted(set(sessions)) or not sessions:
        raise PortfolioError("미국 거래일 목록 오류", "invalid_data")
    if next_session <= sessions[-1]:
        raise PortfolioError("다음 거래일이 마지막 저장일보다 이릅니다.", "invalid_data")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["date", *tickers])
    coverage, extra = {}, {}
    for t in tickers:
        values = quotes.get(t, {})
        extra[t] = sorted(set(values) - set(sessions))
        present = [d for d in sessions if values.get(d) is not None]
        coverage[t] = len(present) / len(sessions)
        if coverage[t] < MIN_COVERAGE:
            raise PortfolioError(f"{t} 관측 비율 {coverage[t]:.3f}가 기준 미달입니다. 기존 자료를 보존합니다.", "invalid_data")
        if values.get(sessions[-1]) is None:
            raise PortfolioError(f"{t} 최신 완료 거래일({sessions[-1]}) 종가가 없습니다. 기존 자료를 보존합니다.",
                                 "provider_delayed", ticker=t, day=sessions[-1])
    for day in sessions:
        row = [day]
        for t in tickers:
            x = quotes.get(t, {}).get(day)
            if x is not None and not (x > 0 and x == x and x != float("inf")):
                raise PortfolioError(f"{t} 비정상 종가 {day}", "invalid_data")
            row.append("" if x is None else repr(float(x)))
        writer.writerow(row)
    raw = stream.getvalue().encode()
    return raw, {
        "schema_version": 1,
        "provider": "Yahoo Finance adjusted close (yfinance auto_adjust=True)",
        "yfinance_version": _version("yfinance"),
        "exchange_calendars_version": _version("exchange_calendars"),
        "tickers": list(tickers),
        "first_date": sessions[0], "last_date": sessions[-1], "rows": len(sessions),
        "next_us_session": next_session,
        "coverage": {t: round(c, 6) for t, c in coverage.items()},
        "missing_sessions": {t: [d for d in sessions if quotes.get(t, {}).get(d) is None] for t in tickers},
        "ignored_non_session_dates": extra,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "use": "overnight overlay experiment and pre-open display only; frozen Risk Score/MSI unchanged",
    }


def _version(name):
    try:
        return version(name)
    except Exception:  # noqa: BLE001 - version is informational only
        return None


def publish(raw, meta, csv_path=DEFAULT_CSV, provenance_path=DEFAULT_PROVENANCE):
    csv_path, provenance_path = Path(csv_path), Path(provenance_path)
    if provenance_path.exists() and csv_path.exists():
        old = json.loads(provenance_path.read_text(encoding="utf-8"))
        same = {k: v for k, v in old.items() if k != "retrieved_at"} == {k: v for k, v in meta.items() if k != "retrieved_at"}
        if same and hashlib.sha256(csv_path.read_bytes()).hexdigest() == meta["sha256"]:
            return old  # no timestamp-only commit
    meta = {**meta, "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=csv_path.parent) as temp:
        stage = Path(temp)
        (stage / csv_path.name).write_bytes(raw)
        (stage / provenance_path.name).write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(stage / csv_path.name, csv_path)
        os.replace(stage / provenance_path.name, provenance_path)
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=START)
    args = parser.parse_args(argv)
    sessions = completed_sessions(args.start, datetime.now(timezone.utc))
    stored = Path(DEFAULT_PROVENANCE)
    stored_last = json.loads(stored.read_text(encoding="utf-8"))["last_date"] if stored.exists() else None
    try:
        quotes = fetch_quotes(list(TICKERS), args.start, sessions[-1])
        raw, meta = build(sessions, quotes, next_session_after(sessions[-1]))
    except PortfolioError as exc:
        # Provider late/unreachable: keep the stored data and retry (qsignals.deferral).
        message = deferral(exc, sessions, stored_last)
        if not message:
            raise
        warn(message)
        return
    meta = publish(raw, meta)
    print(json.dumps({k: meta[k] for k in ("first_date", "last_date", "rows", "next_us_session", "coverage")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
