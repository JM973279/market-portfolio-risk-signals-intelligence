"""Public KOSPI200 closes used only for event returns, never model features."""
from __future__ import annotations

import hashlib
import math
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from qsignals.calendar import load_sessions, valid_date

URL = "https://fchart.stock.naver.com/sise.nhn?symbol=KPI200&timeframe=day&count=500&requestType=0"


def parse_prices(raw, through):
    """Reject the wrong index, duplicates, missing sessions and invalid closes."""
    valid_date(through)
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unexpected XML entity declaration")
    # Expat does not accept this provider's multibyte EUC-KR bytes directly.
    encoding = "euc-kr" if b"EUC-KR" in raw[:150].upper() else "utf-8"
    doc = ET.fromstring(raw.decode(encoding))
    chart = doc.find(".//chartdata")
    if chart is None or chart.get("symbol") != "KPI200" or chart.get("timeframe") != "day":
        raise ValueError("Naver response is not daily KOSPI200")
    prices = {}
    sessions = set(load_sessions())
    for item in chart.findall("item"):
        parts = item.attrib["data"].split("|")
        if len(parts) != 6 or len(parts[0]) != 8:
            raise ValueError("Invalid Naver OHLCV row")
        day = valid_date(f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:]}")
        value = float(parts[4])
        if not math.isfinite(value) or value <= 0 or day in prices:
            raise ValueError("Invalid or duplicate KOSPI200 close")
        if day <= through:
            if day not in sessions:
                raise ValueError(f"KOSPI200 close on a non-session: {day}")
            prices[day] = value
    if not prices or max(prices) != through:
        raise ValueError(f"KOSPI200 price response does not reach {through}")
    required = {d for d in sessions if min(prices) <= d <= through}
    if set(prices) != required:
        raise ValueError("Missing KOSPI200 price session in provider response")
    return prices


def fetch_prices(through):
    request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Oversized KOSPI200 response")
    prices = parse_prices(raw, through)
    return prices, raw, {
        "provider": "Naver Finance", "symbol": "KPI200", "index_name": "KOSPI200",
        "url": URL, "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(raw).hexdigest(), "first_date": min(prices),
        "last_date": max(prices), "rows": len(prices),
        "use": "event-return diagnostics only; frozen Risk Score/MSI inputs unchanged",
    }
