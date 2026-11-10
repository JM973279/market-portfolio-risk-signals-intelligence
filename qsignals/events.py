"""Event annotations: dated market sell-offs with news-reported triggers.

These labels are written after the fact. They explain what the model saw;
they are never model features or tuning targets.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from qsignals.scores import DATE_RE

TRIGGERS = {
    "geopolitics": "지정학",
    "macro_rates": "금리·물가·고용",
    "ai_semis": "AI·반도체 사이클",
    "flows": "수급·차익실현",
    "politics_regulation": "정치·규제",
}

# Amplifiers are the mechanisms that could later be measured as point-in-time
# data (README, step 1). Each maps to a candidate quantitative proxy.
AMPLIFIERS = {
    "foreign_selling": "외국인 순매도",
    "institutional_selling": "기관 순매도",
    "krw_weakness": "원화 약세",
    "margin_debt": "신용융자·개인 레버리지",
    "single_stock_leveraged_etf": "단일종목 레버리지 ETF",
    "hedge_fund_deleveraging": "대형 펀드 디레버리징",
    "oil_price": "유가",
    "pension_rebalancing": "국민연금 리밸런싱",
}

MARKET_HALTS = {"CB", "sidecar"}

SOURCE_QUALITY = {"news", "blog", "mixed", "unsourced"}

# post_hoc_news: written after the event from later reporting (hindsight).
# same_day_log: recorded on the event day before the next open. Only this kind
#   could ever become a point-in-time model input, once enough history exists.
BASIS = {"post_hoc_news", "same_day_log"}

CSV_FIELDS = (
    "event_id",
    "date",
    "index_name",
    "reported_close",
    "reported_change_pct",
    "intraday_note",
    "market_halt",
    "trigger_primary",
    "trigger_secondary",
    "trigger_summary",
    "amplifiers",
    "source_urls",
    "source_quality",
    "basis",
    "recorded_at",
)


@dataclass(frozen=True)
class Event:
    event_id: str
    date: str
    index_name: str
    reported_close: float | None
    reported_change_pct: float | None
    intraday_note: str
    market_halt: tuple[str, ...]
    trigger_primary: str
    trigger_secondary: str
    trigger_summary: str
    amplifiers: tuple[str, ...]
    source_urls: tuple[str, ...]
    source_quality: str
    basis: str
    recorded_at: str


def _split(value):
    return tuple(x.strip() for x in value.split(";") if x.strip())


def _opt_float(value):
    return None if value.strip() == "" else float(value)


def parse_event(rec):
    event = Event(
        event_id=rec["event_id"].strip(),
        date=rec["date"].strip(),
        index_name=rec["index_name"].strip(),
        reported_close=_opt_float(rec["reported_close"]),
        reported_change_pct=_opt_float(rec["reported_change_pct"]),
        intraday_note=rec["intraday_note"].strip(),
        market_halt=_split(rec["market_halt"]),
        trigger_primary=rec["trigger_primary"].strip(),
        trigger_secondary=rec["trigger_secondary"].strip(),
        trigger_summary=rec["trigger_summary"].strip(),
        amplifiers=_split(rec["amplifiers"]),
        source_urls=_split(rec["source_urls"]),
        source_quality=rec["source_quality"].strip(),
        basis=rec["basis"].strip(),
        recorded_at=rec["recorded_at"].strip(),
    )
    validate_event(event)
    return event


def validate_event(e):
    where = e.event_id or "<missing id>"
    if not e.event_id:
        raise ValueError("Missing event_id")
    for name in ("date", "recorded_at"):
        if not DATE_RE.match(getattr(e, name)):
            raise ValueError(f"{where}: bad {name}")
    if e.recorded_at < e.date:
        raise ValueError(f"{where}: recorded before the event date")
    if e.trigger_primary not in TRIGGERS:
        raise ValueError(f"{where}: unknown trigger_primary {e.trigger_primary!r}")
    if e.trigger_secondary and e.trigger_secondary not in TRIGGERS:
        raise ValueError(f"{where}: unknown trigger_secondary {e.trigger_secondary!r}")
    if e.trigger_secondary == e.trigger_primary:
        raise ValueError(f"{where}: secondary trigger repeats the primary")
    if not e.trigger_summary:
        raise ValueError(f"{where}: missing trigger_summary")
    unknown = set(e.amplifiers) - AMPLIFIERS.keys()
    if unknown:
        raise ValueError(f"{where}: unknown amplifiers {sorted(unknown)}")
    unknown = set(e.market_halt) - MARKET_HALTS
    if unknown:
        raise ValueError(f"{where}: unknown market_halt {sorted(unknown)}")
    if e.source_quality not in SOURCE_QUALITY:
        raise ValueError(f"{where}: unknown source_quality {e.source_quality!r}")
    if (e.source_quality == "unsourced") != (not e.source_urls):
        raise ValueError(f"{where}: source_quality and source_urls disagree")
    if any(not u.startswith("https://") for u in e.source_urls):
        raise ValueError(f"{where}: source URLs must be https")
    if e.basis not in BASIS:
        raise ValueError(f"{where}: unknown basis {e.basis!r}")
    if e.basis == "same_day_log" and e.recorded_at != e.date:
        raise ValueError(f"{where}: same_day_log must be recorded on the event date")
    if e.reported_close is None and e.reported_change_pct is None and not e.intraday_note:
        raise ValueError(f"{where}: no reported market move")


def read_events(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise ValueError(f"Unexpected columns: {reader.fieldnames}")
        events = [parse_event(rec) for rec in reader]

    ids = [e.event_id for e in events]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate event_id")
    keys = [(e.index_name, e.date) for e in events]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate index/date event")
    return sorted(events, key=lambda e: e.date)
