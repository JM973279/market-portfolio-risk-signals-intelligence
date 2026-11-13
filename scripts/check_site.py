"""Check a running M/PRI site against the data in this checkout (standard library only).

    python3 scripts/check_site.py http://127.0.0.1:3300            # local image before deploying
    python3 scripts/check_site.py https://<lightsail>.amazonlightsail.com --retries 10

The site passes when every page answers 200 and it serves exactly the data committed here:
- operational-markets.json (Korea/US V1 scores) and korea-preopen.json (overnight US
  reference) are byte-identical to frontend/public/data,
- the Korean and US portfolio APIs report the price dates in data/portfolio-kr and data/portfolio,
- both portfolio analyses return a result in their own currency.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ['/', '/korea', '/us', '/portfolio', '/validation', '/cases', '/sources', '/methodology',
         '/breadth', '/portfolio-lab', '/portfolio-kr-lab']
ANALYSES = {
    'korea': ('/api/portfolio-kr', 'data/portfolio-kr', 'KRW', '005930'),
    'us': ('/api/portfolio', 'data/portfolio', 'USD', 'SPY'),
}


def fetch(base, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {'User-Agent': 'mpri-site-check'} | ({'Content-Type': 'application/json'} if data else {})
    with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=headers), timeout=60) as r:
        return r.status, r.read()


def check(base):
    problems = []
    for page in PAGES:
        try:
            status, _ = fetch(base, page)
            if status != 200:
                problems.append(f'{page}: HTTP {status}')
        except (urllib.error.URLError, OSError) as exc:
            problems.append(f'{page}: {exc}')
    for name in ('operational-markets.json', 'korea-preopen.json'):
        expected = (ROOT / 'frontend/public/data' / name).read_bytes()
        try:
            _, served = fetch(base, '/data/' + name)
            if served != expected:
                problems.append(f'{name} differs from this checkout')
        except (urllib.error.URLError, OSError) as exc:
            problems.append(f'{name}: {exc}')
    dates = {}
    for market, (api, folder, currency, ticker) in ANALYSES.items():
        current = ROOT / folder / 'current.json'
        if not current.exists():
            continue  # A market without published data shows its "data needed" state instead.
        want = json.loads(current.read_text())['price_as_of']
        try:
            _, raw = fetch(base, api + '/meta')
            end = json.loads(raw)['coverage']['end']
            if end != want:
                problems.append(f'{market} portfolio serves {end}, checkout has {want}')
            _, raw = fetch(base, api + '/analyze',
                           {'holdings': [{'ticker': ticker, 'weight': 100}], 'initial_value_usd': 1000})
            result = json.loads(raw)
            if result.get('currency') != currency or 'summary' not in result:
                problems.append(f'{market} analysis did not return a {currency} result')
            dates[market] = end
        except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            problems.append(f'{market} portfolio API: {exc}')
    operational = json.loads(expected)['markets']
    dates.update({f'{m}_score_due': operational[m].get('expectedDate') for m in operational})
    return problems, dates


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('base_url')
    parser.add_argument('--retries', type=int, default=1, help='attempts, 20 s apart (a new deployment warms up)')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    for attempt in range(1, args.retries + 1):
        problems, dates = check(base)
        if not problems:
            print('site check passed: ' + json.dumps(dates, sort_keys=True))
            return 0
        print(f'attempt {attempt}/{args.retries}: ' + '; '.join(problems), file=sys.stderr)
        if attempt < args.retries:
            time.sleep(20)
    return 1


if __name__ == '__main__':
    sys.exit(main())
