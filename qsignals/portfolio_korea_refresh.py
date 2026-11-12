"""Actions-only Korean portfolio collection; the deployed API reads GitHub snapshots."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from qsignals.calendar import latest_closed_session, load_sessions, require_coverage, valid_date
from qsignals.portfolio_data import PortfolioError, load_dataset, parse_files
from qsignals.portfolio_import import publish
from qsignals.portfolio_refresh import csv_bytes, fetch_quotes
from scripts.build_korea_portfolio import MARKET, UNIVERSE, window_extreme

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'data' / 'portfolio-kr'
SOURCE_REPO = 'JM973279/market-portfolio-risk-signals-intelligence'
POLICY = 'korea-portfolio-github-actions-v1'
START = '2018-01-02'


def completed_sessions(now):
    end = latest_closed_session(now, publication_lag_hours=2)
    require_coverage(START, end)
    return [d for d in load_sessions() if START <= d <= end]


def request_json(url, *, headers=None):
    """Do not expose ECOS URLs (which contain the key) in exception text or logs."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code in (401, 403):
                raise PortfolioError('Provider rejected the Actions API key.', 'collection_failed') from None
        except (OSError, ValueError):
            pass
        if attempt < 2:
            time.sleep(attempt + 1)
    raise PortfolioError('Provider request failed; previous snapshot was preserved.', 'collection_failed') from None


def parse_vkospi(raw):
    rows = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not {'Date', 'Close'} <= set(rows.fieldnames or []):
        raise PortfolioError('Invalid VKOSPI cache schema.', 'invalid_data')
    values = {}
    for row in rows:
        day = valid_date(row['Date'])
        if day in values or row.get('Index', 'VKOSPI') != 'VKOSPI':
            raise PortfolioError('Duplicate date or wrong index in VKOSPI cache.', 'invalid_data')
        value = float(row['Close'])
        if not math.isfinite(value) or value <= 0:
            raise PortfolioError('Invalid VKOSPI observation.', 'invalid_data')
        values[day] = value
    return values


def fetch_vkospi(sessions, key, cache=None, previous=None):
    values, origin = {}, 'KRX Open API'
    if cache and Path(cache).exists():
        values = parse_vkospi(Path(cache).read_bytes())
        origin = 'GitHub Actions V1 raw-history cache + KRX Open API'
    elif previous and (Path(previous) / 'current.json').exists():
        # Read only a receipt whose hash and snapshot path have already been verified.
        data = load_dataset(previous)
        record = data.provenance['collection']['receipts']['krx-vkospi.csv']
        values = parse_vkospi((Path(previous) / record['path']).read_bytes())
        origin = 'Verified GitHub receipt + KRX Open API'
    for day in sessions:
        if day in values:
            continue
        payload = request_json(
            'http://data-dbg.krx.co.kr/svc/apis/idx/drvprod_dd_trd?basDd=' + day.replace('-', ''),
            headers={'AUTH_KEY': key})
        for row in payload.get('OutBlock_1', []):
            if row.get('IDX_NM') == '코스피 200 변동성지수':
                if row.get('BAS_DD') != day.replace('-', ''):
                    raise PortfolioError('KRX returned a different observation date.', 'invalid_data')
                values[day] = float(str(row['CLSPRC_IDX']).replace(',', ''))
                break
        time.sleep(0.2)
    return {d: values[d] for d in sessions if d in values}, origin


def parse_ecos(payload):
    rows = payload.get('StatisticSearch', {}).get('row', [])
    if not rows or any('10년' not in r.get('ITEM_NAME1', '') for r in rows):
        raise PortfolioError('ECOS did not return Korea Treasury 10Y.', 'invalid_data')
    result = {}
    for row in rows:
        stamp = row['TIME']
        day = valid_date(f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}')
        value = float(row['DATA_VALUE'])
        if day in result or not math.isfinite(value):
            raise PortfolioError('Duplicate or nonfinite ECOS observation.', 'invalid_data')
        result[day] = value
    return result


def fetch_rates(start, end, key):
    payload = request_json('https://ecos.bok.or.kr/api/StatisticSearch/' + key +
        '/json/kr/1/100000/817Y002/D/' + start.replace('-', '') + '/' +
        end.replace('-', '') + '/010210000')
    return parse_ecos(payload)


def build_snapshot(quotes, rates, volatility, sessions):
    """Keep the KRX calendar and missing observations; never fill or remove sessions."""
    if len(sessions) < 758 or sessions != sorted(set(sessions)):
        raise PortfolioError('At least 758 ordered unique KRX sessions are required.', 'invalid_data')
    for day in sessions:
        valid_date(day)
    tickers = [u[0] for u in UNIVERSE]
    missing = {}
    for ticker in tickers:
        series = quotes.get(ticker, {})
        for value in series.values():
            if not math.isfinite(value) or value <= 0:
                raise PortfolioError('Nonpositive or nonfinite adjusted price.', 'invalid_data', ticker=ticker)
        absent = [d for d in sessions if d not in series]
        if sessions[-1] in absent or len(absent) > len(sessions) * .05:
            raise PortfolioError('Incomplete adjusted-price history; publication blocked.',
                                 'missing_price', ticker=ticker)
        if ticker == MARKET and absent:
            raise PortfolioError('KODEX 200 must cover every completed KRX session.', 'missing_price')
        if absent:
            missing[ticker] = absent
    for name, series in [('KTB10Y', rates), ('VKOSPI', volatility)]:
        if any(not math.isfinite(v) or (name == 'VKOSPI' and v <= 0) for v in series.values()):
            raise PortfolioError('Invalid factor observation.', 'invalid_data', factor=name)
    common = [d for d in sessions if d in rates and d in volatility]
    if not common:
        raise PortfolioError('No common observed factor date.', 'invalid_data')
    risk_end = common[-1]
    lag = len([d for d in sessions if d > risk_end])
    if lag > 3:
        raise PortfolioError('Korean risk factors are over three sessions late.', 'stale_data')
    window = [d for d in sessions if d <= risk_end][-756:]
    if len(window) != 756 or sum(d in common for d in window) < 756 * .95:
        raise PortfolioError('Insufficient observed factors in the 756-session risk window.', 'invalid_data')
    end = sessions[-1]
    market = quotes[MARKET]
    shocks = [('equity_selloff', 'Equity Sell-off', '국내 주식시장 급락', 'market', 'return',
               '스냅샷 기간 중 KODEX 200 10거래일 수익률의 최저값', market),
              ('rate_shock', 'Interest Rate Shock', '국고채 10년 금리 급등', 'rate', 'bp',
               '스냅샷 기간 중 국고채 10년 10거래일 변화(bp)의 최고값', rates),
              ('volatility_shock', 'Volatility Shock', 'VKOSPI 급등', 'volatility', 'pt',
               '스냅샷 기간 중 VKOSPI 10거래일 변화(pt)의 최고값', volatility)]
    scenarios = []
    for ident, name, definition, factor, unit, rule, series in shocks:
        shock, start, finish = window_extreme(sessions, series, unit)
        scenarios.append({'id': ident, 'name': name, 'definition': definition, 'factor': factor,
                          'unit': unit, 'rule': rule, 'shock': round(shock, 6),
                          'reference': {'start': start, 'end': finish}})
    meta = {'market': 'korea', 'currency': 'KRW', 'as_of': end, 'start': sessions[0],
            'window_start': window[0], 'window_end': risk_end, 'window_days': 756,
            'scenario_as_of': end, 'risk_as_of': risk_end, 'refresh_policy': POLICY,
            'price_source': 'Yahoo Finance adjusted close (auto_adjust=True, .KS)',
            'rate_source': 'Bank of Korea ECOS 817Y002/010210000 Korea Treasury 10Y, %',
            'vol_source': 'KRX Open API VKOSPI', 'price_basis': 'dividend_split_adjusted_close'}
    raw = {
        'universe.csv': csv_bytes(['ticker', 'name', 'type', 'sector', 'asset_class'], UNIVERSE),
        'prices.csv': csv_bytes(['Date', *tickers],
            [[d, *(quotes[t].get(d, '') for t in tickers)] for d in sessions]),
        'factors.csv': csv_bytes(['Date', 'VKOSPI', 'KTB10Y'],
            [[d, volatility.get(d, ''), rates.get(d, '')] for d in sessions]),
        'snapshot_meta.json': (json.dumps(meta, ensure_ascii=False, indent=2) + '\n').encode(),
        'scenarios.json': (json.dumps({'as_of': end, 'lookback_start': sessions[0],
            'horizon_days': 10, 'scenarios': scenarios,
            'note': '사전에 정한 충격 가정에 따른 추정치이며 미래 손실 예측이 아닙니다.'},
            ensure_ascii=False, indent=2) + '\n').encode(),
    }
    parse_files(raw, {})
    return raw, {'price_as_of': end, 'risk_as_of': risk_end, 'factor_lag_sessions': lag,
                 'rows': len(sessions), 'assets': len(tickers), 'missing_price_dates': missing,
                 'missing_factor_dates': {k: [d for d in sessions if d not in v]
                                          for k, v in [('VKOSPI', volatility), ('KTB10Y', rates)]}}


def refresh(output=OUTPUT, *, cache=None, now=None, source_commit=None):
    now = now or datetime.now(timezone.utc)
    for key in ['KRX_API_KEY', 'ECOS_API_KEY']:
        if not os.environ.get(key, '').strip():
            raise PortfolioError('Required Actions secret is missing: ' + key, 'collection_failed')
    sessions = completed_sessions(now)
    commit = source_commit or os.environ.get('GITHUB_SHA') or subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    symbols = [row[0] + '.KS' for row in UNIVERSE]
    print('Collecting Korean adjusted prices for ' + str(len(symbols)) + ' assets.', file=sys.stderr)
    downloaded = fetch_quotes(symbols, sessions[0], sessions[-1])
    quotes = {t[:-3]: values for t, values in downloaded.items()}
    volatility, vol_origin = fetch_vkospi(sessions, os.environ['KRX_API_KEY'], cache, output)
    rates = fetch_rates(sessions[0], sessions[-1], os.environ['ECOS_API_KEY'])
    raw, quality = build_snapshot(quotes, rates, volatility, sessions)
    current = Path(output) / 'current.json'
    if current.exists():
        old = load_dataset(output)
        if quality['price_as_of'] < old.meta['as_of'] or quality['risk_as_of'] < old.meta['risk_as_of']:
            raise PortfolioError('Refusing to move published Korean observation dates backwards.', 'stale_data')
    receipts = {
        'yahoo-adjusted-close.csv': raw['prices.csv'],
        'krx-vkospi.csv': csv_bytes(['Date', 'Close'], [[d, volatility[d]] for d in sessions if d in volatility]),
        'ecos-ktb10y.csv': csv_bytes(['Date', 'KTB10Y'], [[d, rates[d]] for d in sorted(rates)]),
        'krx-sessions.csv': csv_bytes(['Date'], [[d] for d in sessions]),
    }
    collection = {'policy': POLICY, 'retrieved_at': now.isoformat(timespec='seconds'),
                  'code_repo': SOURCE_REPO, 'code_ref': 'main', 'code_commit': commit,
                  'github_run_id': os.environ.get('GITHUB_RUN_ID'),
                  'providers': {'prices': 'Yahoo Finance adjusted close', 'volatility': vol_origin,
                                'rates': 'Bank of Korea ECOS 817Y002/010210000'},
                  'calendar_sha256': hashlib.sha256((ROOT / 'data/calendar/xkrx_sessions.csv').read_bytes()).hexdigest(),
                  'normalization': 'full adjusted-price vintage; KRX sessions retained; no filling', **quality}
    manifest = publish(raw, SOURCE_REPO, commit, output, collection=collection,
                       receipts=receipts, source_paths={})
    data = load_dataset(output)
    if data.meta['market'] != 'korea' or data.provenance['currency'] != 'KRW':
        raise PortfolioError('Published snapshot market/currency mismatch.', 'invalid_data')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT)
    parser.add_argument('--vkospi-cache', type=Path)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    try:
        if not args.validate_only:
            refresh(args.output_dir, cache=args.vkospi_cache)
        data = load_dataset(args.output_dir)
        assert data.meta['market'] == 'korea' and data.provenance['currency'] == 'KRW'
        print(json.dumps({'snapshot': data.provenance['snapshot_id'], 'market': 'korea',
                          'currency': 'KRW', 'price_as_of': data.meta['as_of'],
                          'risk_as_of': data.meta['risk_as_of'], 'assets': len(data.universe)}))
    except Exception as exc:
        # Provider exceptions may contain private URLs. Publish only our own sanitized messages.
        print(str(exc) if isinstance(exc, PortfolioError) else type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
