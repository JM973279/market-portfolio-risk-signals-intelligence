import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from qsignals.portfolio_replay import build_windows, compute_replay, replay_window

DAYS = [(date(2026, 1, 5) + timedelta(days=i)).isoformat() for i in range(30)]


def dataset(prices=None, horizon=3):
    prices = prices or {d: {'SPY': 100 + i, 'AAA': 50 - i / 2, 'BBB': 20.0} for i, d in enumerate(DAYS)}
    scenarios = {'horizon_days': horizon, 'scenarios': [
        {'id': 'equity_selloff', 'name': 'Equity Sell-off', 'definition': '주식시장 급락',
         'factor': 'market', 'shock': -0.2, 'reference': {'start': DAYS[2], 'end': DAYS[6]}}]}
    return SimpleNamespace(days=DAYS, prices=prices, scenarios=scenarios)


def episode(eid, geo='foreign', reference=DAYS[10], tier='core'):
    metrics = None if reference is None else {'reference_date': reference, 'onset_return': -0.05, 'max_drawdown': -0.12}
    return {'id': eid, 'name': {'en': eid, 'ko': eid}, 'geo': geo, 'tier': tier, 'onset': reference or DAYS[0],
            'category': 'macro_news', 'metrics': metrics}


class ReplayTest(unittest.TestCase):
    def test_windows_are_fixed_by_inputs(self):
        library = {'episodes': [episode('foreign'), episode('home', geo='domestic'), episode('late', reference=DAYS[-1]),
                                episode('unpriced', reference=None)]}
        windows, excluded = build_windows(DAYS, dataset().scenarios, library, 3)
        self.assertEqual([w['id'] for w in windows], ['equity_selloff', 'foreign'])
        korea = windows[1]
        self.assertEqual(korea['start'], DAYS[9])  # last US close strictly before the KRX reference close
        self.assertEqual(korea['end'], DAYS[12])
        self.assertEqual({e['id']: e['reason'] for e in excluded},
                         {'home': 'domestic_source', 'late': 'outside_snapshot', 'unpriced': 'no_reference_date'})

    def test_buy_and_hold_math_and_signs(self):
        data = dataset()
        window = {'id': 'w', 'group': 'factor_reference', 'name_en': 'w', 'name_ko': 'w', 'start': DAYS[2], 'end': DAYS[6],
                  'linked_scenario': 'equity_selloff', 'korea': None}
        row = replay_window({'AAA': 0.5, 'BBB': 0.5}, 100000, data.prices, DAYS, window)
        aaa = (50 - 6 / 2) / (50 - 2 / 2) - 1  # AAA falls, BBB flat
        self.assertAlmostEqual(row['return'], round(0.5 * aaa, 6))
        self.assertAlmostEqual(row['pnl_usd'], round(100000 * 0.5 * aaa, 2))
        self.assertLess(row['return'], 0)  # loss is negative, matching the rest of the module
        self.assertEqual(row['worst_date'], DAYS[6])
        self.assertAlmostEqual(row['spy_return'], round(106 / 102 - 1, 6))
        self.assertEqual(row['sessions'], 4)

    def test_missing_price_excludes_window(self):
        prices = {d: {'SPY': 100.0, 'AAA': 10.0} for d in DAYS}
        prices[DAYS[4]]['AAA'] = None
        with tempfile.TemporaryDirectory() as d:
            result = compute_replay(dataset(prices), {'AAA': 1.0}, 1000, korea_path=Path(d) / 'missing.json')
        self.assertEqual(result['results'], [])
        self.assertEqual(result['excluded'][0]['reason'], 'missing_price')
        self.assertFalse(result['korea_library_available'])

    def test_korea_library_used_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'korea-scenarios.json'
            path.write_text(json.dumps({'schema_version': 1, 'asOf': '2026-10-02', 'episodes': [episode('foreign')]}),
                            encoding='utf-8')
            result = compute_replay(dataset(), {'AAA': 1.0}, 1000, korea_path=path)
        self.assertTrue(result['korea_library_available'])
        self.assertEqual([r['group'] for r in result['results']], ['factor_reference', 'korea_library'])
        self.assertEqual(result['results'][1]['korea']['kospi200_max_drawdown'], -0.12)
        self.assertFalse(result['methodology']['scenarios_additive'])
        self.assertFalse(result['methodology']['is_forecast'])


if __name__ == '__main__':
    unittest.main()
