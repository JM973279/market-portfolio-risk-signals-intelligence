"""Per-market portfolio settings: US unchanged by default, Korea on its own anchors."""
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from qsignals.portfolio import analyze, describe
from qsignals.portfolio_data import PortfolioError, parse_files
from qsignals.portfolio_replay import build_windows, compute_replay

DAYS = [d.isoformat() for d in (date(2026, 1, 5) + timedelta(days=i) for i in range(60)) if d.weekday() < 5]
TICKERS = ('005930', '069500', '148070', '132030')


def csv(rows):
    return ('\n'.join(','.join(map(str, r)) for r in rows) + '\n').encode()


def korea_raw(market='korea'):
    universe = [('ticker', 'name', 'type', 'sector', 'asset_class'), ('005930', '삼성전자', 'stock', '반도체', 'equity'),
                ('069500', 'KODEX 200', 'etf', '지수', 'equity'), ('148070', 'KOSEF 국고채10년', 'etf', '국고채', 'bond'),
                ('132030', 'KODEX 골드선물(H)', 'etf', '금', 'commodity')]
    prices = [('Date', *TICKERS)] + [(d, 100 + i * (1 + (i % 3)), 100 + i, 100 - i / 10, 100 + (i % 5)) for i, d in enumerate(DAYS)]
    factors = [('Date', 'VKOSPI', 'KTB10Y')] + [(d, 20 + (i % 7), 3 + (i % 4) / 100) for i, d in enumerate(DAYS)]
    meta = {'as_of': DAYS[-1], 'window_start': DAYS[5], 'window_end': DAYS[-1], 'scenario_as_of': DAYS[-1]}
    if market:
        meta['market'] = market
    scenarios = {'as_of': DAYS[-1], 'horizon_days': 3, 'scenarios': [
        {'id': 'equity_selloff', 'name': 'Equity Sell-off', 'definition': '국내 주식시장 급락', 'factor': 'market',
         'shock': -0.2, 'reference': {'start': DAYS[2], 'end': DAYS[6]}}]}
    return {'universe.csv': csv(universe), 'prices.csv': csv(prices), 'factors.csv': csv(factors),
            'snapshot_meta.json': json.dumps(meta).encode(), 'scenarios.json': json.dumps(scenarios).encode()}


class KoreaProfileTest(unittest.TestCase):
    def test_korea_snapshot_uses_its_own_anchor_currency_and_factors(self):
        data = parse_files(korea_raw(), {'source_commit': 'a' * 40})
        meta = describe(data)
        self.assertEqual(meta['market']['currency'], 'KRW')
        self.assertEqual(meta['market']['market_ticker'], '069500')
        self.assertIn('kodex200', meta['benchmarks'])
        r = analyze(data, {'holdings': [{'ticker': '005930', 'weight': 100}], 'initial_value_usd': 10_000_000,
                           'start': DAYS[0], 'end': DAYS[-1]})
        self.assertEqual(r['benchmark']['id'], 'kodex200')
        self.assertEqual(r['currency'], 'KRW')
        self.assertTrue(any('KRW' in a for a in r['assumptions']))
        self.assertEqual(r['risk']['status'], 'available')
        self.assertIsNotNone(r['risk']['factor_exposure']['volatility'])  # VKOSPI column, not VIX
        self.assertEqual(r['attribution']['asset_class']['status'], 'available')

    def test_korea_snapshot_requires_korean_reference_assets(self):
        raw = korea_raw()
        raw['universe.csv'] = raw['universe.csv'].replace(b'132030', b'999999')
        raw['prices.csv'] = raw['prices.csv'].replace(b'132030', b'999999')
        with self.assertRaises(PortfolioError):
            parse_files(raw, {'source_commit': 'a' * 40})

    def test_snapshot_without_market_stays_us(self):
        # The Korean files without "market" are read as US and fail on the missing SPY/IEF/GLD.
        with self.assertRaises(PortfolioError) as caught:
            parse_files(korea_raw(market=None), {'source_commit': 'a' * 40})
        self.assertIn('SPY', str(caught.exception))

    def test_unknown_market_is_rejected(self):
        with self.assertRaises(PortfolioError):
            parse_files(korea_raw(market='mars'), {'source_commit': 'a' * 40})

    def test_korea_replay_keeps_domestic_episodes_and_starts_at_reference_close(self):
        ep = {'id': 'home', 'name': {'en': 'home', 'ko': 'home'}, 'geo': 'domestic', 'tier': 'core', 'onset': DAYS[11],
              'category': 'policy', 'metrics': {'reference_date': DAYS[10], 'onset_return': -.05, 'max_drawdown': -.1}}
        scen = {'scenarios': []}
        us, us_excluded = build_windows(DAYS, scen, {'episodes': [ep]}, 3)
        kr, _ = build_windows(DAYS, scen, {'episodes': [ep]}, 3, domestic_sessions=True)
        self.assertEqual(us, [])
        self.assertEqual(us_excluded[0]['reason'], 'domestic_source')
        self.assertEqual(kr[0]['start'], DAYS[10])
        data = parse_files(korea_raw(), {'source_commit': 'a' * 40})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'lib.json'
            path.write_text(json.dumps({'schema_version': 1, 'episodes': [ep]}), encoding='utf-8')
            result = compute_replay(data, {'005930': 1.0}, 1000, korea_path=path)
        row = next(r for r in result['results'] if r['group'] == 'korea_library')
        prices = data.prices
        self.assertAlmostEqual(row['spy_return'], round(prices[DAYS[13]]['069500'] / prices[DAYS[10]]['069500'] - 1, 6))


if __name__ == '__main__':
    unittest.main()
