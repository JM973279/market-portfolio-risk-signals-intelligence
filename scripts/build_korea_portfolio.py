"""Explicit local option: build a Korea portfolio snapshot (KRW, KRX sessions).

Not the default operating path (see AGENTS.md). Run it on your own machine with your own
keys; the output directory is gitignored and must not be committed or shared, because
the providers do not allow redistribution:
- prices: Yahoo Finance adjusted close (dividends and splits), <code>.KS
- volatility: VKOSPI from your own KRX Open API raw cache (V1 download_vkospi.py)
- rate: Korea Treasury 10Y from the Bank of Korea ECOS API (your ECOS_API_KEY)

No filling: a KRX session where a listed asset has no Yahoo price is dropped for all
assets and recorded in the manifest. Standard library only.

    python3 scripts/build_korea_portfolio.py --env-file <V1 .env> --vkospi <vkospi.csv>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / 'data' / 'portfolio-kr'
CALENDAR = ROOT / 'data' / 'calendar' / 'xkrx_sessions.csv'
KST = timezone(timedelta(hours=9))
UA = {'User-Agent': 'Mozilla/5.0'}
WINDOW_DAYS = 756
HORIZON = 10

# ticker, name, type, sector, asset_class. KOSPI listings, all on Yahoo as <code>.KS.
UNIVERSE = [
    ('005930', '삼성전자', 'stock', '반도체', 'equity'),
    ('000660', 'SK하이닉스', 'stock', '반도체', 'equity'),
    ('005380', '현대차', 'stock', '자동차', 'equity'),
    ('000270', '기아', 'stock', '자동차', 'equity'),
    ('012330', '현대모비스', 'stock', '자동차', 'equity'),
    ('035420', 'NAVER', 'stock', '인터넷', 'equity'),
    ('035720', '카카오', 'stock', '인터넷', 'equity'),
    ('051910', 'LG화학', 'stock', '화학·2차전지', 'equity'),
    ('006400', '삼성SDI', 'stock', '화학·2차전지', 'equity'),
    ('068270', '셀트리온', 'stock', '바이오', 'equity'),
    ('207940', '삼성바이오로직스', 'stock', '바이오', 'equity'),
    ('105560', 'KB금융', 'stock', '금융', 'equity'),
    ('055550', '신한지주', 'stock', '금융', 'equity'),
    ('005490', 'POSCO홀딩스', 'stock', '철강', 'equity'),
    ('066570', 'LG전자', 'stock', '전자', 'equity'),
    ('017670', 'SK텔레콤', 'stock', '통신', 'equity'),
    ('033780', 'KT&G', 'stock', '필수소비재', 'equity'),
    ('069500', 'KODEX 200', 'etf', '국내 대형주 지수', 'equity'),
    ('229200', 'KODEX 코스닥150', 'etf', '국내 중소형주 지수', 'equity'),
    ('133690', 'TIGER 미국나스닥100', 'etf', '해외주식 (원화)', 'equity'),
    ('148070', 'KOSEF 국고채10년', 'etf', '국고채 10년', 'bond'),
    ('114260', 'KODEX 국고채3년', 'etf', '국고채 3년', 'bond'),
    ('132030', 'KODEX 골드선물(H)', 'etf', '금 (환헤지)', 'commodity'),
]
MARKET = '069500'


def get(url, attempts=3):
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))


def yahoo_adjusted(code, start, end):
    p1 = int(datetime.fromisoformat(start).replace(tzinfo=KST).timestamp())
    p2 = int((datetime.fromisoformat(end) + timedelta(days=1)).replace(tzinfo=KST).timestamp())
    raw = get(f'https://query1.finance.yahoo.com/v8/finance/chart/{code}.KS?period1={p1}&period2={p2}'
              '&interval=1d&events=div,split&includeAdjustedClose=true')
    res = json.loads(raw)['chart']['result'][0]
    offset = res['meta'].get('gmtoffset', 32400)
    days = [datetime.fromtimestamp(t + offset, timezone.utc).strftime('%Y-%m-%d') for t in res['timestamp']]
    adj = res['indicators']['adjclose'][0]['adjclose']
    out = {d: float(v) for d, v in zip(days, adj) if v is not None and math.isfinite(v) and v > 0}
    return out, hashlib.sha256(raw).hexdigest()


def ecos_ktb10y(key, start, end):
    url = (f'https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100000/817Y002/D/'
           f'{start.replace("-", "")}/{end.replace("-", "")}/010210000')
    payload = json.loads(get(url))
    rows = payload.get('StatisticSearch', {}).get('row', [])
    if not rows or '10년' not in rows[0].get('ITEM_NAME1', ''):
        raise ValueError('ECOS 817Y002/010210000 is not 국고채(10년)')
    return {f'{r["TIME"][:4]}-{r["TIME"][4:6]}-{r["TIME"][6:]}': float(r['DATA_VALUE']) for r in rows}


def read_env(path):
    values = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def csv_bytes(fields, rows):
    s = io.StringIO(newline='')
    w = csv.writer(s, lineterminator='\n')
    w.writerow(fields)
    w.writerows(rows)
    return s.getvalue().encode()


def window_extreme(days, series, kind):
    """Worst 10-session move: min return (market) or max change (rate/vol). Returns (shock, start, end)."""
    best = None
    for i in range(len(days) - HORIZON):
        a, b = series.get(days[i]), series.get(days[i + HORIZON])
        if a is None or b is None:
            continue
        move = b / a - 1 if kind == 'return' else b - a
        if kind == 'bp':
            move *= 100
        score = -move if kind == 'return' else move
        if best is None or score > best[0]:
            best = (score, move, days[i], days[i + HORIZON])
    return best[1], best[2], best[3]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, default=DEFAULT_OUT)
    p.add_argument('--start', default='2018-01-02')
    p.add_argument('--env-file', type=Path, help='file with ECOS_API_KEY (else the environment)')
    p.add_argument('--vkospi', type=Path, required=True, help='VKOSPI raw CSV from your KRX download')
    a = p.parse_args(argv)

    now = datetime.now(KST)
    today = now.strftime('%Y-%m-%d')
    sessions = [r['date'] for r in csv.DictReader(io.StringIO(CALENDAR.read_text(encoding='utf-8')))]
    # Only completed sessions: today's counts after 16:00 KST (KRX closes 15:30).
    last_allowed = today if now.hour >= 16 else (now - timedelta(days=1)).strftime('%Y-%m-%d')
    sessions = [d for d in sessions if a.start <= d <= last_allowed]

    quotes, receipts = {}, {}
    for code, *_ in UNIVERSE:
        quotes[code], receipts[code] = yahoo_adjusted(code, a.start, last_allowed)
        print(f'{code}: {len(quotes[code])} rows, {min(quotes[code])}..{max(quotes[code])}', file=sys.stderr)
        time.sleep(0.5)
    last = max(quotes[MARKET])
    sessions = [d for d in sessions if d <= last]
    first = {c: min(q) for c, q in quotes.items()}
    dropped, kept = [], []
    for d in sessions:
        missing = [c for c in quotes if d >= first[c] and d not in quotes[c]]
        (dropped.append({'date': d, 'missing': missing}) if missing else kept.append(d))
    off_calendar = {c: sorted(set(q) - set(sessions)) for c, q in quotes.items()}
    off_calendar = {c: v for c, v in off_calendar.items() if v}

    env = read_env(a.env_file) if a.env_file else os.environ
    key = env.get('ECOS_API_KEY', '').strip()
    rates, rate_note = {}, None
    if key:
        try:
            rates = ecos_ktb10y(key, a.start, last)
        except (OSError, ValueError, KeyError) as exc:
            rate_note = f'ECOS 수집 실패: {type(exc).__name__}'
    else:
        rate_note = 'ECOS_API_KEY 없음'
    vk = {r['Date']: float(r['Close']) for r in csv.DictReader(io.StringIO(a.vkospi.read_text(encoding='utf-8-sig')))
          if r.get('Close')}

    prices = csv_bytes(['Date', *[c for c, *_ in UNIVERSE]],
                       [[d, *[('' if d < first[c] else repr(quotes[c][d])) for c, *_ in UNIVERSE]] for d in kept])
    factors = csv_bytes(['Date', 'VKOSPI', 'KTB10Y'],
                        [[d, vk.get(d, ''), rates.get(d, '')] for d in kept])
    universe = csv_bytes(['ticker', 'name', 'type', 'sector', 'asset_class'], [list(u) for u in UNIVERSE])

    risk_days = [d for d in kept if d in vk and (d in rates or not rates)]
    window_end = risk_days[-1]
    window = [d for d in kept if d <= window_end][-WINDOW_DAYS:]
    market = {d: quotes[MARKET][d] for d in kept}
    m = window_extreme(kept, market, 'return')
    r = window_extreme(kept, rates, 'bp') if rates else None
    v = window_extreme(kept, vk, 'pt')
    scen = [{'id': 'equity_selloff', 'name': 'Equity Sell-off', 'definition': '국내 주식시장 급락', 'factor': 'market',
             'unit': 'return', 'rule': '스냅샷 기간 중 KODEX 200 10거래일 수익률의 최저값', 'shock': round(m[0], 4),
             'reference': {'start': m[1], 'end': m[2]}}]
    if r:
        scen.append({'id': 'rate_shock', 'name': 'Interest Rate Shock', 'definition': '국고채 10년 금리 급등',
                     'factor': 'rate', 'unit': 'bp', 'rule': '스냅샷 기간 중 국고채 10년 10거래일 변화(bp)의 최고값',
                     'shock': round(r[0], 2), 'reference': {'start': r[1], 'end': r[2]}})
    scen.append({'id': 'volatility_shock', 'name': 'Volatility Shock', 'definition': 'VKOSPI 급등', 'factor': 'volatility',
                 'unit': 'pt', 'rule': '스냅샷 기간 중 VKOSPI 10거래일 변화(pt)의 최고값', 'shock': round(v[0], 2),
                 'reference': {'start': v[1], 'end': v[2]}})
    as_of = kept[-1]
    scenarios = json.dumps({'as_of': as_of, 'lookback_start': kept[0], 'horizon_days': HORIZON,
                            'note': '사전에 정한 충격 가정에 따른 추정치이며 미래 손실 예측이 아닙니다.',
                            'scenarios': scen}, ensure_ascii=False, indent=2).encode()
    meta = json.dumps({'market': 'korea', 'currency': 'KRW', 'as_of': as_of, 'start': kept[0],
                       'window_start': window[0], 'window_end': window[-1], 'window_days': len(window),
                       'price_source': 'Yahoo Finance adjusted close (chart API adjclose, <code>.KS)',
                       'rate_source': 'Bank of Korea ECOS 817Y002 국고채(10년), %' if rates else None,
                       'vol_source': 'KRX Open API VKOSPI close (local raw cache)',
                       'scenario_as_of': as_of, 'risk_as_of': window[-1],
                       'price_basis': 'dividend_split_adjusted_close'}, ensure_ascii=False, indent=2).encode()

    files = {'prices.csv': prices, 'factors.csv': factors, 'universe.csv': universe,
             'snapshot_meta.json': meta, 'scenarios.json': scenarios}
    snapshot = hashlib.sha1(b''.join(hashlib.sha256(files[n]).digest() for n in sorted(files))).hexdigest()
    folder = a.out / 'snapshots' / snapshot
    folder.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        (folder / name).write_bytes(raw)
    manifest = {'schema_version': 2, 'market': 'korea', 'source_repo': 'local:korea-portfolio-demo',
                'source_commit': snapshot, 'snapshot_id': snapshot, 'currency': 'KRW',
                'price_basis': 'dividend_split_adjusted_close',
                'display_source': f'로컬 수집 (Yahoo 수정종가 · KRX VKOSPI · ECOS 국고채) · 팀 내부 시험용 · {now.isoformat(timespec="minutes")}',
                'files': {n: {'path': f'snapshots/{snapshot}/{n}', 'sha256': hashlib.sha256(raw).hexdigest()}
                          for n, raw in files.items()},
                'imported_at': now.isoformat(timespec='seconds'),
                'collection': {'policy': 'korea-local-demo-v1', 'retrieved_at': now.isoformat(timespec='seconds'),
                               'providers': {'prices': 'Yahoo Finance chart API adjclose', 'volatility': 'KRX VKOSPI',
                                             'rates': 'ECOS 국고채(10년)' if rates else rate_note},
                               'raw_sha256': receipts, 'dropped_sessions': dropped,
                               'off_calendar_rows': {c: len(v) for c, v in off_calendar.items()},
                               'rows': len(kept), 'assets': len(UNIVERSE), 'price_as_of': as_of,
                               'risk_as_of': window[-1], 'rate_note': rate_note},
                'sector_attribution': {'status': 'unavailable', 'reason': '한국 섹터 벤치마크 자료가 연결되지 않았습니다.'}}
    (a.out / 'current.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'snapshot': snapshot, 'as_of': as_of, 'rows': len(kept), 'dropped': len(dropped),
                      'window': [window[0], window[-1]], 'rate_rows': len(rates), 'rate_note': rate_note,
                      'off_calendar': {c: len(v) for c, v in off_calendar.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
