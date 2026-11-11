"""V1 Risk Score series (Korea for the event diagnostics, US for comparison).

The deployed project (market-portfolio-risk-intelligence) is read-only from
here. `qsignals.import_scores` refreshes the Korea series from its frozen
frontend exports and records SHA-256 provenance; everything else in this
project works from that copy (data/input/korea_scores.csv, us_scores.csv).
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

from qsignals.calendar import valid_date

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# OOS_WALK_FORWARD: expanding walk-forward OOS prediction (global-markets.json)
# RETROSPECTIVE_INFERENCE / OPERATIONAL: frozen V1 model (training cutoff
#   2026-09-16) applied to later dates (operational-markets.json)
# NO_SCORE: the date exists in a source but has no Risk Score
RECORD_TYPES = (
    "OOS_WALK_FORWARD",
    "RETROSPECTIVE_INFERENCE",
    "OPERATIONAL",
    "NO_SCORE",
)

CSV_FIELDS = (
    "date",
    "kospi200_close",
    "risk_v1",
    "msi",
    "stress_threshold",
    "record_type",
)

# Each market's CSV names its own equity close column; the rest is shared.
MARKETS = ("korea", "us")
PRICE_COLUMNS = {"korea": "kospi200_close", "us": "spy_close"}


def csv_fields(market="korea"):
    return ("date", PRICE_COLUMNS[market], *CSV_FIELDS[2:])


@dataclass(frozen=True)
class ScoreRow:
    date: str
    kospi200_close: float | None  # the market's equity close (SPY for US rows)
    risk_v1: float | None
    msi: float | None
    stress_threshold: float | None
    record_type: str


def _num(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a market observation")
    x = float(value)
    if not math.isfinite(x):
        raise ValueError(f"Non-finite value: {value!r}")
    return x


def validate_rows(rows):
    previous = ""
    for row in rows:
        valid_date(row.date)
        if row.date <= previous:
            raise ValueError(
                f"Dates must be unique and ascending: {previous} -> {row.date}"
            )
        previous = row.date
        for value in (row.kospi200_close, row.risk_v1, row.msi, row.stress_threshold):
            if value is not None:
                _num(value)
        if row.record_type not in RECORD_TYPES:
            raise ValueError(f"Unknown record type on {row.date}: {row.record_type}")
        if (row.risk_v1 is None) != (row.record_type == "NO_SCORE"):
            raise ValueError(f"Risk/record type mismatch on {row.date}")
        if row.risk_v1 is not None and not 0.0 <= row.risk_v1 <= 1.0:
            raise ValueError(f"Risk outside 0-1 on {row.date}: {row.risk_v1}")
        if row.kospi200_close is not None and row.kospi200_close <= 0:
            raise ValueError(f"Non-positive price on {row.date}")
    return rows


def build_rows(global_markets, operational, prices=None, market="korea"):
    """Merge the walk-forward OOS series with the frozen-model series.

    Walk-forward OOS rows take precedence on any shared date. Operational rows
    only fill dates without an OOS score. Independent diagnostic prices can
    fill missing closes after reconciliation with the frozen price history.
    """

    by_date = {}

    for item in global_markets[market]:
        if item["date"] in by_date:
            raise ValueError(f"Duplicate research date: {item['date']}")
        risk = _num(item.get("risk"))
        by_date[item["date"]] = ScoreRow(
            date=item["date"],
            kospi200_close=_num(item.get("price")),
            risk_v1=risk,
            msi=_num(item.get("msi")),
            stress_threshold=_num(item.get("threshold")),
            record_type="OOS_WALK_FORWARD" if risk is not None else "NO_SCORE",
        )

    validate_rows(list(by_date.values()))
    seen = set()
    previous = ""
    source = operational["markets"][market]
    for item in source["history"]:
        date = item["date"]
        valid_date(date)
        if date in seen or date <= previous:
            raise ValueError(f"Duplicate or unordered operational date: {date}")
        seen.add(date)
        previous = date
        risk = _num(item.get("risk"))
        kind = item.get("recordType") if risk is not None else "NO_SCORE"
        validate_rows([ScoreRow(date, None, risk, _num(item.get("msi")),
                                _num(item.get("threshold")), kind)])
        if risk is not None and kind not in ("OPERATIONAL", "RETROSPECTIVE_INFERENCE"):
            raise ValueError("Operational input cannot claim walk-forward OOS")
        if risk is not None and source.get("trainingCutoff") and date <= source["trainingCutoff"]:
            raise ValueError("Frozen-model score is not after its training cutoff")
        existing = by_date.get(date)
        if existing is not None and existing.risk_v1 is not None:
            continue
        by_date[date] = ScoreRow(
            date=date,
            kospi200_close=existing.kospi200_close if existing else None,
            risk_v1=risk,
            msi=_num(item.get("msi")),
            stress_threshold=_num(item.get("threshold")),
            record_type=kind,
        )

    # Price enrichment changes only event returns, never the frozen score/MSI.
    for day, price in (prices or {}).items():
        valid_date(day)
        price = _num(price)
        existing = by_date.get(day)
        if existing and existing.kospi200_close is not None:
            if abs(price - existing.kospi200_close) > 0.005:
                raise ValueError(f"Price provider disagrees with frozen reference on {day}")
        elif existing:
            by_date[day] = ScoreRow(**{**existing.__dict__, "kospi200_close": price})
        else:
            by_date[day] = ScoreRow(day, price, None, None, None, "NO_SCORE")
    return validate_rows([by_date[d] for d in sorted(by_date)])


def write_scores(rows, path, market="korea"):
    validate_rows(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(csv_fields(market))
        for r in rows:
            writer.writerow(
                [
                    r.date,
                    "" if r.kospi200_close is None else repr(r.kospi200_close),
                    "" if r.risk_v1 is None else repr(r.risk_v1),
                    "" if r.msi is None else repr(r.msi),
                    "" if r.stress_threshold is None else repr(r.stress_threshold),
                    r.record_type,
                ]
            )


def read_scores(path, market="korea"):
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = csv_fields(market)
        if tuple(reader.fieldnames or ()) != fields:
            raise ValueError(f"Unexpected columns: {reader.fieldnames}")
        rows = [
            ScoreRow(
                date=rec["date"],
                kospi200_close=_num(rec[fields[1]]),
                risk_v1=_num(rec["risk_v1"]),
                msi=_num(rec["msi"]),
                stress_threshold=_num(rec["stress_threshold"]),
                record_type=rec["record_type"],
            )
            for rec in reader
        ]
    return validate_rows(rows)
