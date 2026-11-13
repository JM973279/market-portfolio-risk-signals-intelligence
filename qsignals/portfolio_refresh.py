"""Actions-only full-vintage portfolio collection; web inputs remain GitHub files."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import time
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

from qsignals.deferral import deferral, warn
from qsignals.import_scores import DEFAULT_REPO
from qsignals.portfolio_data import DEFAULT_DATA, FILES, PortfolioError, parse_files
from qsignals.portfolio_import import fetch_upstream, publish

POLICY = 'portfolio-full-provider-vintage-v1'


def csv_bytes(fields, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(fields)
    writer.writerows(rows)
    return stream.getvalue().encode()


def parse_fred(raw):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if reader.fieldnames not in (['observation_date', 'DGS10'], ['DATE', 'DGS10']):
        raise PortfolioError('FRED DGS10 응답 열이 다릅니다.', 'invalid_data')
    date_key = reader.fieldnames[0]
    result = {}
    from qsignals.portfolio_data import iso_day
    for row in reader:
        day = iso_day(row[date_key])
        if day in result:
            raise PortfolioError('FRED 관측일 중복', 'invalid_data')
        value = None if row['DGS10'] in ('', '.') else float(row['DGS10'])
        if value is not None and not math.isfinite(value):
            raise PortfolioError('FRED 비정상 값', 'invalid_data')
        result[day] = value
    return result


def completed_sessions(start, now):
    import pandas as pd
    import exchange_calendars as xcals
    if now.tzinfo is None:
        raise PortfolioError('시간대가 있는 현재 시각이 필요합니다.')
    cal = xcals.get_calendar('XNYS', start=start, end=f'{now.year + 1}-12-31')
    schedule = cal.schedule
    # Wait two hours after the actual (including early) close for adjusted EOD bars.
    ready = schedule[schedule['close'] + timedelta(hours=2) <= pd.Timestamp(now)]
    if ready.empty:
        raise PortfolioError('완료된 미국 세션이 없습니다.', 'invalid_data')
    return [d.strftime('%Y-%m-%d') for d in ready.index]


def fetch_quotes(tickers, start, end):
    import yfinance as yf
    import pandas as pd
    yf.set_tz_cache_location('/tmp/mqs-portfolio-yahoo-cache')
    frame = None
    for attempt in range(3):
        frame = yf.download(tickers, start=start,
                            end=(datetime.fromisoformat(end) + timedelta(days=1)).date().isoformat(),
                            auto_adjust=True, threads=False, progress=False, timeout=30)
        if frame is not None and not frame.empty and 'Close' in frame:
            close = frame['Close']
            if isinstance(close, pd.Series):
                close = close.to_frame(tickers[0])
            if all(t in close.columns and close[t].notna().any() for t in tickers):
                break
        if attempt < 2:
            time.sleep(attempt + 1)
    else:
        raise PortfolioError('Yahoo 전체 자산 수집 실패. 기존 검증 자료를 보존합니다.', 'collection_failed')
    quotes = {}
    for ticker in tickers:
        quotes[ticker] = {stamp.strftime('%Y-%m-%d'): float(value)
                          for stamp, value in close[ticker].dropna().items()}
    return quotes


def fetch_fred(start, end):
    import requests
    url = 'https://fred.stlouisfed.org/graph/fredgraph.csv'
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, params={'id': 'DGS10', 'cosd': start, 'coed': end}, timeout=(10, 30))
            response.raise_for_status()
            raw = response.content
            parse_fred(raw)
            return raw
        except (requests.RequestException, TimeoutError, PortfolioError, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    raise PortfolioError('FRED DGS10 수집 실패. 기존 검증 자료를 보존합니다.', 'collection_failed') from last_error


def build_snapshot(seed_raw, quotes, rates, sessions):
    """Pure validation/normalization; no interpolation, no old/new price splicing."""
    seed = parse_files(seed_raw, {})
    start = seed.meta['start']
    days = [d for d in sessions if d >= start]
    if len(days) < 758:
        raise PortfolioError('위험 추정을 위한 충분한 전체 이력이 필요합니다.', 'invalid_data')
    if days != sorted(set(days)):
        raise PortfolioError('세션 중복·정렬 오류', 'invalid_data')
    tickers = sorted(seed.universe)
    for ticker in [*tickers, '^VIX']:
        for day in days:
            value = quotes.get(ticker, {}).get(day)
            if value is None or not math.isfinite(value) or value <= 0:
                raise PortfolioError('완료 거래일 가격이 누락되었습니다. 이전 값으로 채우지 않습니다.',
                                     'missing_price', ticker=ticker, date=day)
    risk_days = [d for d in days if rates.get(d) is not None]
    if not risk_days:
        raise PortfolioError('검증된 금리 자료가 없습니다.', 'invalid_data')
    risk_end = risk_days[-1]
    rate_lag = len([d for d in days if d > risk_end])
    if rate_lag > 3:
        raise PortfolioError('금리 자료가 3거래일을 넘게 지연됐습니다.', 'stale_data')
    window = [d for d in days if d <= risk_end][-756:]
    if len(window) != 756:
        raise PortfolioError('위험 추정 756거래일이 부족합니다.', 'invalid_data')
    if days[-1] < seed.meta['as_of']:
        raise PortfolioError('가격 기준일의 역행을 거부합니다.', 'stale_data')
    for d in days:
        value = rates.get(d)
        if value is not None and not math.isfinite(value):
            raise PortfolioError('금리 비정상 값', 'invalid_data')
    meta = {**seed.meta, 'as_of': days[-1], 'start': days[0],
            'window_start': window[0], 'window_end': risk_end, 'window_days': len(window),
            'scenario_as_of': seed.scenarios['as_of'], 'risk_as_of': risk_end,
            'refresh_policy': POLICY, 'price_basis': 'dividend_split_adjusted_close'}
    raw = {**seed_raw,
           'prices.csv': csv_bytes(['Date', *tickers], [[d, *(quotes[t][d] for t in tickers)] for d in days]),
           'factors.csv': csv_bytes(['Date', 'VIX', 'DGS10'],
                                   [[d, quotes['^VIX'][d], rates.get(d, '') if rates.get(d) is not None else ''] for d in days]),
           'snapshot_meta.json': (json.dumps(meta, ensure_ascii=False, indent=2) + '\n').encode()}
    parse_files(raw, {})
    differences = {}
    for ticker in tickers:
        compared = [(d, seed.prices[d][ticker], quotes[ticker][d]) for d in seed.days
                    if d in quotes[ticker] and seed.prices[d].get(ticker) is not None]
        changes = [abs(a - b) for _, a, b in compared]
        differences[ticker] = {'compared': len(compared),
                               'changed': sum(abs(a - b) > 1e-6 for _, a, b in compared),
                               'max_abs_difference': max(changes, default=0)}
    return raw, {'price_as_of': days[-1], 'risk_as_of': risk_end,
                 'rate_lag_sessions': rate_lag, 'rows': len(days), 'assets': len(tickers),
                 'adjusted_price_revision_audit': differences}


def refresh(repo=DEFAULT_REPO, ref='main', output=DEFAULT_DATA, *, now=None, replay=None):
    now = now or datetime.now(timezone.utc)
    recorded = json.loads(Path(replay).read_text()) if replay else None
    if recorded and recorded['source_repo'] != repo:
        raise PortfolioError('재현 원본 저장소가 현재 설정과 다릅니다.', 'invalid_data')
    seed_ref = recorded['source_commit'] if recorded else ref
    seed_raw, source_commit = fetch_upstream(repo, seed_ref)
    seed = parse_files(seed_raw, {})
    if replay:
        # Explicit offline provider replay; GitHub seed is still pinned independently.
        m = json.loads(Path(replay).read_text())
        files = {}
        for name, record in m['collection']['receipts'].items():
            content = (Path(replay).parent / record['path']).read_bytes()
            if hashlib.sha256(content).hexdigest() != record['sha256']:
                raise PortfolioError('재현 수집 기록 해시 불일치', 'invalid_data')
            files[name] = content
        rows = list(csv.DictReader(io.StringIO(files['yahoo-adjusted-close.csv'].decode())))
        quotes = {t: {r['Date']: float(r[t]) for r in rows} for t in rows[0] if t != 'Date'}
        rates = parse_fred(files['fred-dgs10.csv'])
        sessions = [r['Date'] for r in csv.DictReader(io.StringIO(files['nyse-sessions.csv'].decode()))]
        retrieved_at = m['collection']['retrieved_at']
    else:
        sessions = completed_sessions(seed.meta['start'], now)
        quotes = fetch_quotes([*sorted(seed.universe), '^VIX'], seed.meta['start'], sessions[-1])
        fred_raw = fetch_fred(seed.meta['start'], sessions[-1])
        rates = parse_fred(fred_raw)
        symbols = [*sorted(seed.universe), '^VIX']
        files = {'yahoo-adjusted-close.csv': csv_bytes(['Date', *symbols],
                    [[d, *(quotes[t].get(d, '') for t in symbols)] for d in sessions]),
                 'fred-dgs10.csv': fred_raw,
                 'nyse-sessions.csv': csv_bytes(['Date'], [[d] for d in sessions])}
        retrieved_at = now.isoformat(timespec='seconds')
    previous_path = Path(output) / 'current.json'
    previous_as_of = json.loads(previous_path.read_text())['price_as_of'] if previous_path.exists() else None
    try:
        raw, quality = build_snapshot(seed_raw, quotes, rates, sessions)
    except PortfolioError as exc:
        # Yahoo sometimes blanks a daily bar it served earlier. If that session is already
        # verified in the published snapshot, keep it and skip publication; never fill.
        day = exc.details.get('date')
        if exc.code == 'missing_price' and previous_as_of and day and day <= previous_as_of:
            raise PortfolioError(f'Yahoo withheld already-verified session {day} '
                                 f'({exc.details.get("ticker")}); kept published snapshot {previous_as_of}.',
                                 'provider_withheld', **exc.details) from None
        raise
    collection = {'policy': POLICY, 'retrieved_at': retrieved_at,
                  'seed_repo': repo, 'seed_ref': ref, 'seed_commit': source_commit,
                  'seed_files': {n: hashlib.sha256(v).hexdigest() for n, v in seed_raw.items()},
                  'providers': {'prices': 'Yahoo Finance adjusted close (yfinance auto_adjust=True)',
                                'rates': 'FRED DGS10 (no filling)', 'calendar': 'XNYS completed close + 2h'},
                  'versions': {p: version(p) for p in ('yfinance', 'pandas', 'numpy', 'exchange_calendars', 'requests', 'curl_cffi')},
                  'normalization': 'full-history single provider vintage; no cached-price splicing',
                  **quality}
    if previous_as_of:
        if quality['price_as_of'] < previous_as_of:
            raise PortfolioError('기존 발행본보다 오래된 자료는 게시하지 않습니다.', 'stale_data')
    manifest = publish(raw, repo, source_commit, output, collection=collection, receipts=files)
    print(json.dumps({'price_as_of': manifest['price_as_of'],
                      'risk_as_of': manifest['collection']['risk_as_of'],
                      'assets': manifest['collection']['assets'],
                      'snapshot_id': manifest['snapshot_id'], 'source_repo': manifest['source_repo']}, ensure_ascii=False))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-repo', default=DEFAULT_REPO)
    parser.add_argument('--source-ref', default='main')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    try:
        refresh(args.source_repo, args.source_ref, args.output_dir, replay=args.replay)
    except PortfolioError as exc:
        # Provider late/unreachable: keep the published snapshot and retry (qsignals.deferral).
        message = None if args.replay else deferral(exc, *_published_position(args.output_dir))
        if not message:
            raise
        warn(message)


def _published_position(output):
    """(completed XNYS sessions of the last two months, published price date or None)."""
    now = datetime.now(timezone.utc)
    current = Path(output) / 'current.json'
    published = json.loads(current.read_text())['price_as_of'] if current.exists() else None
    return completed_sessions((now - timedelta(days=60)).strftime('%Y-%m-%d'), now), published


if __name__ == '__main__':
    main()
