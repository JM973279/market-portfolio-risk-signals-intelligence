import copy
import json
import math
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from qsignals.portfolio import analyze, brinson_fachler, describe, holdings
from qsignals.portfolio_data import Dataset, PortfolioError, load_dataset
from qsignals.portfolio_import import publish, import_remote


def sample():
    universe = {t: {'ticker': t, 'name': t, 'type': 'stock' if t in ('A', 'B') else 'etf',
                   'sector': 'Technology' if t != 'IEF' else 'Treasury',
                   'asset_class': 'bond' if t == 'IEF' else 'commodity' if t == 'GLD' else 'equity'}
                for t in ('A', 'B', 'SPY', 'IEF', 'GLD')}
    prices = {
        '2026-01-02': {'A': 100., 'B': 100., 'SPY': 100., 'IEF': 100., 'GLD': 100.},
        '2026-01-05': {'A': 200., 'B': 100., 'SPY': 110., 'IEF': 95., 'GLD': 100.},
        '2026-01-06': {'A': 100., 'B': 200., 'SPY': 112., 'IEF': 104., 'GLD': 100.},
    }
    return Dataset(prices, {}, universe,
                   {'as_of': '2026-01-06', 'window_start': '2026-01-02', 'window_end': '2026-01-06'},
                   {'scenarios': []}, {'source_commit': 'a'*40})


def request(**kwargs):
    return {'holdings': [{'ticker': 'A', 'weight': 50}, {'ticker': 'B', 'weight': 50}],
            'initial_value_usd': 100000, 'start': '2026-01-02', 'end': '2026-01-06', **kwargs}


class PerformanceTest(unittest.TestCase):
    def test_buy_and_hold_does_not_rebalance_daily(self):
        result = analyze(sample(), request())
        # Constant-weight daily compounding would yield +62.5%, not +50%.
        self.assertAlmostEqual(result['summary']['return'], .5)
        self.assertAlmostEqual(result['summary']['pnl_usd'], 50000)
        self.assertAlmostEqual(sum(a['contribution'] for a in result['by_asset']), .5)
        self.assertEqual(result['risk']['status'], 'unavailable')
        self.assertEqual(result['attribution']['equity_sector']['status'], 'unavailable')

    def test_spy_against_itself_is_zero_active(self):
        r = analyze(sample(), request(holdings=[{'ticker': 'SPY', 'weight': 100}]))
        self.assertAlmostEqual(r['summary']['active_return'], 0)
        a = r['attribution']['asset_class']
        self.assertEqual([a[k] for k in ('allocation', 'selection', 'interaction')], [0, 0, 0])

    def test_drawdown_includes_start_and_peak(self):
        r = analyze(sample(), request(holdings=[{'ticker': 'A', 'weight': 100}]))
        self.assertEqual(r['summary']['return'], 0)
        self.assertEqual(r['summary']['max_drawdown'], -.5)

    def test_loss_contributions_and_zero_return_are_finite(self):
        d = sample()
        d.prices['2026-01-06'].update(A=90., B=110.)
        r = analyze(d, request())
        self.assertAlmostEqual(r['summary']['return'], 0)
        self.assertTrue(any(a['contribution'] < 0 for a in r['by_asset']))
        json.dumps(r, allow_nan=False)

    def test_missing_intermediate_price_is_not_filled(self):
        d = sample(); d.prices['2026-01-05']['A'] = None
        with self.assertRaises(PortfolioError) as c:
            analyze(d, request())
        self.assertEqual(c.exception.code, 'missing_price')
        self.assertEqual(c.exception.details['date'], '2026-01-05')

    def test_weekend_start_uses_next_observed_trading_day(self):
        r = analyze(sample(), request(start='2026-01-03'))
        self.assertEqual(r['requested_period']['start'], '2026-01-03')
        self.assertEqual(r['effective_period']['start'], '2026-01-05')

    def test_outside_coverage_never_silently_truncates(self):
        with self.assertRaises(PortfolioError) as c:
            analyze(sample(), request(end='2026-01-07'))
        self.assertEqual(c.exception.code, 'outside_coverage')

    def test_invalid_dates_weights_and_nonfinite_rejected(self):
        for change in ({'start': '2026-02-30'}, {'initial_value_usd': True},
                       {'initial_value_usd': math.inf}, {'initial_value_usd': -1},
                       {'holdings': [{'ticker': 'A', 'weight': 90}]},
                       {'holdings': [{'ticker': 'A', 'weight': 50}, {'ticker': 'A', 'weight': 50}]},
                       {'holdings': [{'ticker': 'UNKNOWN', 'weight': 100}]}):
            with self.subTest(change=change), self.assertRaises(PortfolioError):
                analyze(sample(), request(**change))

    def test_allowed_rounding_is_normalized(self):
        w = holdings([{'ticker': 'A', 'weight': 33.33}, {'ticker': 'B', 'weight': 66.66}], sample().universe)
        self.assertAlmostEqual(sum(w.values()), 1)

    def test_compare_uses_union_and_same_dates(self):
        r = analyze(sample(), request(proposed_holdings=[{'ticker': 'IEF', 'weight': 100}]))
        c = r['comparison']
        self.assertTrue(c['same_period'])
        self.assertEqual([p['date'] for p in r['series']], [p['date'] for p in c['proposed']['series']])
        self.assertAlmostEqual(c['proposed']['summary']['return'], .04)
        d = sample();d.prices['2026-01-05']['IEF'] = None
        with self.assertRaises(PortfolioError):
            analyze(d, request(proposed_holdings=[{'ticker': 'IEF', 'weight': 100}]))

    def test_custom_benchmark_and_balanced_hold_without_rebalance(self):
        r = analyze(sample(), request(benchmark={'kind': 'balanced'}))
        self.assertAlmostEqual(r['summary']['benchmark_return'], .6*.12+.4*.04)
        r = analyze(sample(), request(benchmark={'kind': 'custom', 'holdings': request()['holdings']}))
        self.assertAlmostEqual(r['summary']['active_return'], 0)


class AttributionTest(unittest.TestCase):
    def test_synthetic_sector_example_reconciles(self):
        p = {'tech': {'weight': .8, 'return': .1875}, 'consumer': {'weight': .2, 'return': -.05}}
        b = {'tech': {'weight': .6, 'return': .10}, 'consumer': {'weight': .4, 'return': .15}}
        r = brinson_fachler(p, b)
        for key, expected in [('active_return', .02), ('allocation', -.01),
                              ('selection', -.0275), ('interaction', .0575), ('residual', 0)]:
            self.assertAlmostEqual(r[key], expected)

    def test_same_weights_zero_allocation_and_interaction(self):
        p = {'equity': {'weight': .6, 'return': .2}, 'bond': {'weight': .4, 'return': .04}}
        b = {'equity': {'weight': .6, 'return': .1}, 'bond': {'weight': .4, 'return': .03}}
        r = brinson_fachler(p, b)
        self.assertEqual(r['allocation'], 0)
        self.assertEqual(r['interaction'], 0)
        self.assertAlmostEqual(r['selection'], r['active_return'])

    def test_unheld_group_has_no_made_up_selection(self):
        p = {'equity': {'weight': 1., 'return': .2}}
        b = {'equity': {'weight': .6, 'return': .1}, 'bond': {'weight': .4, 'return': .03}}
        r = brinson_fachler(p, b)
        bond = next(g for g in r['by_group'] if g['group'] == 'bond')
        self.assertEqual(bond['selection'], 0)
        self.assertEqual(bond['interaction'], 0)
        self.assertAlmostEqual(r['residual'], 0)

    def test_off_benchmark_reference_is_required(self):
        p = {'equity': {'weight': .7, 'return': .14}, 'bond': {'weight': .3, 'return': .04}}
        b = {'equity': {'weight': 1., 'return': .12}}
        with self.assertRaises(PortfolioError):
            brinson_fachler(p, b)
        r = brinson_fachler(p, b, off_benchmark_returns={'bond': .04})
        self.assertAlmostEqual(r['allocation'], -.024)
        self.assertAlmostEqual(r['selection'], .02)
        self.assertAlmostEqual(r['interaction'], -.006)
        self.assertAlmostEqual(r['active_return'], -.01)

    def test_mixed_asset_allocation_nonzero(self):
        p = {'equity': {'weight': .8, 'return': .175}, 'bond': {'weight': .2, 'return': 0}}
        b = {'equity': {'weight': .6, 'return': .15}, 'bond': {'weight': .4, 'return': .05}}
        r = brinson_fachler(p, b)
        self.assertAlmostEqual(r['active_return'], .03)
        self.assertAlmostEqual(r['allocation'], .02)
        self.assertAlmostEqual(r['selection'], -.005)
        self.assertAlmostEqual(r['interaction'], .015)

    def test_degenerate_and_invalid_weights(self):
        with self.assertRaises(PortfolioError):
            brinson_fachler({'a': {'weight': .9, 'return': 0}}, {'a': {'weight': 1, 'return': 0}})
        same = {'a': {'weight': 1, 'return': 0}}
        self.assertEqual(brinson_fachler(same, same)['active_return'], 0)


class BundledDataTest(unittest.TestCase):
    def test_real_snapshot_risk_reconciles(self):
        d = load_dataset()
        r = analyze(d, {'holdings': describe(d)['example'], 'initial_value_usd': 100000})
        self.assertEqual(r['risk']['status'], 'available')
        self.assertAlmostEqual(sum(a['share'] for a in r['risk']['risk_contribution']), 1)
        self.assertEqual(r['provenance']['price_as_of'], r['effective_period']['end'])
        self.assertAlmostEqual(sum(a['contribution'] for a in r['by_asset']), r['summary']['return'])
        for scenario in r['risk']['stress']:
            self.assertAlmostEqual(sum(a['pnl_usd'] for a in scenario['by_asset']), scenario['pnl_usd'])
        json.dumps(r, allow_nan=False)

    def test_hash_mismatch_rejected_and_failed_import_preserves_current(self):
        from qsignals.portfolio_data import FILES, DEFAULT_DATA
        manifest = json.loads((DEFAULT_DATA/'current.json').read_text())
        raw = {name: (DEFAULT_DATA/manifest['files'][name]['path']).read_bytes() for name in FILES}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            publish(raw, manifest['source_repo'], 'a'*40, out)
            before = (out/'current.json').read_bytes()
            malformed = {**raw, 'prices.csv': b'Date,SPY\n2026-01-01,NaN\n'}
            with self.assertRaises(PortfolioError):
                publish(malformed, manifest['source_repo'], 'b'*40, out)
            self.assertEqual((out/'current.json').read_bytes(), before)
            path = out/'snapshots'/('a'*40)/'prices.csv'
            path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaises(PortfolioError):
                load_dataset(out)

    def test_same_input_does_not_change_receipt(self):
        from qsignals.portfolio_data import FILES, DEFAULT_DATA
        m = json.loads((DEFAULT_DATA/'current.json').read_text())
        raw = {name: (DEFAULT_DATA/m['files'][name]['path']).read_bytes() for name in FILES}
        with tempfile.TemporaryDirectory() as tmp:
            publish(raw, m['source_repo'], 'c'*40, tmp)
            first = (Path(tmp)/'current.json').read_bytes()
            publish(raw, m['source_repo'], 'c'*40, tmp)
            self.assertEqual((Path(tmp)/'current.json').read_bytes(), first)
            publish(raw, m['source_repo'], 'e'*40, tmp)
            self.assertEqual((Path(tmp)/'current.json').read_bytes(), first)

    def test_remote_files_are_pinned_to_one_sha(self):
        from qsignals.portfolio_data import FILES, DEFAULT_DATA
        m = json.loads((DEFAULT_DATA/'current.json').read_text())
        raw = {name: (DEFAULT_DATA/m['files'][name]['path']).read_bytes() for name in FILES}
        urls=[]
        def download(url):
            urls.append(url)
            return json.dumps({'sha': 'd'*40}).encode() if '/commits/' in url else raw[url.rsplit('/',1)[-1]]
        with tempfile.TemporaryDirectory() as tmp, patch('qsignals.portfolio_import._download',side_effect=download):
            import_remote(output=tmp)
        self.assertEqual(len(urls), 6)
        self.assertTrue(all('/'+('d'*40)+'/' in url for url in urls[1:]))


class SectorAdapterTest(unittest.TestCase):
    def record(self):
        return {'period': {'start': '2026-01-02', 'end': '2026-01-06'},
                'benchmark_weights': {'SPY': 1.0}, 'price_snapshot_sha': 'a'*40,
                'currency': 'USD', 'return_basis': 'dividend_split_adjusted_close',
                'classification_policy': 'fixed_start_point_in_time',
                'classification_as_of': '2026-01-02',
                'classifications': {'A': 'tech', 'B': 'consumer'},
                'benchmark_groups': {'tech': {'weight': .6, 'return': .1},
                                     'consumer': {'weight': .4, 'return': .15}},
                'sources': [{'url': 'https://example.com/receipt', 'sha256': 'synthetic test only'}]}

    def test_exact_period_point_in_time_sector_adapter(self):
        from dataclasses import replace
        d=replace(sample(), sector_records=(self.record(),))
        a=analyze(d,request())['attribution']['equity_sector']
        self.assertEqual(a['status'],'available')
        self.assertAlmostEqual(a['active_return'],.38)
        self.assertAlmostEqual(a['allocation'],.005)
        self.assertAlmostEqual(a['selection'],.28)
        self.assertAlmostEqual(a['interaction'],.095)
        self.assertAlmostEqual(a['residual'],0)

    def test_wrong_version_period_and_benchmark_sum_blocked(self):
        from dataclasses import replace
        for key,value in [('price_snapshot_sha','b'*40),('classification_as_of','2026-01-01'),
                          ('period',{'start':'2026-01-05','end':'2026-01-06'}),
                          ('benchmark_groups',{'tech':{'weight':1.,'return':.1}})]:
            record=self.record();record[key]=value
            a=analyze(replace(sample(),sector_records=(record,)),request())['attribution']['equity_sector']
            self.assertEqual(a['status'],'unavailable')

    def test_corrupt_optional_sector_receipt_preserves_main_analysis(self):
        from qsignals.portfolio_sectors import load_sector_records
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            record=self.record();record['sources']=[{'path':'../secret','url':'https://example.com/x','sha256':'x'}]
            (root/'sector-inputs.json').write_text(json.dumps({'schema_version':1,'records':[record]}))
            self.assertIn('adapter_error',load_sector_records(root)[0])
