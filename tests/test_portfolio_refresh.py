import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qsignals.portfolio_data import DEFAULT_DATA, FILES, PortfolioError, load_dataset, parse_files
from qsignals.portfolio_import import publish
from qsignals.portfolio_refresh import build_snapshot, csv_bytes, parse_fred, refresh


def fixture():
    m = json.loads((DEFAULT_DATA/'current.json').read_text())
    raw = {name: (DEFAULT_DATA/m['files'][name]['path']).read_bytes() for name in FILES}
    seed = parse_files(raw, {})
    # Real immutable historical fixture + five explicit mock observations, never published as live data.
    extra = ['2026-10-26','2026-10-27','2026-10-28','2026-10-29','2026-10-30']
    # Keep the fixture valid if a newer actual snapshot is already bundled.
    from datetime import date, timedelta
    cursor = date.fromisoformat(seed.days[-1]); extra=[]
    while len(extra)<5:
        cursor += timedelta(days=1)
        if cursor.weekday()<5: extra.append(cursor.isoformat())
    days = seed.days + extra
    quotes = {t: {d: seed.prices[d][t] for d in seed.days} for t in seed.universe}
    quotes['^VIX'] = {d: seed.factors[d]['VIX'] for d in seed.days}
    for t, values in quotes.items():
        for index, d in enumerate(extra): values[d] = values[seed.days[-1]]*(1+.001*(index+1))
    rates = {d: seed.factors[d]['DGS10'] for d in seed.days}
    rates.update({d: 4. for d in extra[:-1]})
    return m, raw, quotes, rates, days


class PortfolioRefreshTest(unittest.TestCase):
    def test_latest_price_and_risk_dates_are_separate(self):
        _, seed, quotes, rates, days = fixture()
        raw, quality=build_snapshot(seed,quotes,rates,days)
        data=parse_files(raw,{})
        self.assertEqual(data.meta['as_of'],days[-1])
        self.assertEqual(data.meta['window_end'],days[-2])
        self.assertEqual(quality['rate_lag_sessions'],1)
        self.assertEqual(raw['scenarios.json'],seed['scenarios.json'])
        self.assertEqual(data.meta['scenario_as_of'],json.loads(seed['scenarios.json'])['as_of'])
        self.assertIsNone(data.factors[days[-1]]['DGS10'])

    def test_revised_full_vintage_not_spliced_onto_old_history(self):
        _, seed, quotes, rates, days=fixture()
        first=days[0];quotes['AAPL'][first]*=1.01
        raw, quality=build_snapshot(seed,quotes,rates,days)
        self.assertEqual(parse_files(raw,{}).prices[first]['AAPL'],quotes['AAPL'][first])
        self.assertGreater(quality['adjusted_price_revision_audit']['AAPL']['changed'],0)

    def test_missing_asset_or_intermediate_bar_fails(self):
        for ticker,offset in [('AAPL',-1),('SPY',10),('^VIX',-2)]:
            _, seed, quotes, rates, days=fixture()
            del quotes[ticker][days[offset]]
            with self.subTest(ticker=ticker),self.assertRaises(PortfolioError):
                build_snapshot(seed,quotes,rates,days)

    def test_stale_rate_and_nonfinite_values_fail(self):
        _,seed,quotes,rates,days=fixture()
        for d in days[-4:]:rates.pop(d,None)
        with self.assertRaises(PortfolioError):build_snapshot(seed,quotes,rates,days)
        _,seed,quotes,rates,days=fixture();quotes['SPY'][days[-1]]=float('nan')
        with self.assertRaises(PortfolioError):build_snapshot(seed,quotes,rates,days)

    def test_new_snapshot_identity_and_receipts_preserve_seed(self):
        m,seed,quotes,rates,days=fixture();raw,quality=build_snapshot(seed,quotes,rates,days)
        with tempfile.TemporaryDirectory() as tmp:
            publish(seed,m['source_repo'],m['source_commit'],tmp)
            original=(Path(tmp)/'current.json').read_bytes()
            manifest=publish(raw,m['source_repo'],m['source_commit'],tmp,
                             collection={'policy':'test-only',**quality},receipts={'response.csv':b'provider receipt\n'})
            self.assertEqual(manifest['source_commit'],m['source_commit'])
            self.assertNotEqual(manifest['snapshot_id'],m['source_commit'])
            self.assertTrue((Path(tmp)/'snapshots'/m['source_commit']/'prices.csv').exists())
            self.assertEqual(load_dataset(tmp).meta['as_of'],days[-1])
            stable=(Path(tmp)/'current.json').read_bytes()
            publish(raw,m['source_repo'],m['source_commit'],tmp,collection={'policy':'test-only',**quality},
                    receipts={'response.csv':b'provider receipt\n'})
            self.assertEqual((Path(tmp)/'current.json').read_bytes(),stable)
            receipt=next(iter(manifest['collection']['receipts'].values()))
            (Path(tmp)/receipt['path']).write_bytes(b'tampered')
            with self.assertRaises(PortfolioError):load_dataset(tmp)
            self.assertNotEqual(original,stable)

    def test_collection_failure_keeps_previous_current(self):
        m,raw,quotes,rates,days=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            publish(raw,m['source_repo'],m['source_commit'],tmp)
            before=(Path(tmp)/'current.json').read_bytes()
            with patch('qsignals.portfolio_refresh.fetch_upstream',return_value=(raw,m['source_commit'])), \
                 patch('qsignals.portfolio_refresh.completed_sessions',return_value=days), \
                 patch('qsignals.portfolio_refresh.fetch_quotes',side_effect=PortfolioError('provider failed')):
                with self.assertRaises(PortfolioError):refresh(output=tmp)
            self.assertEqual((Path(tmp)/'current.json').read_bytes(),before)

    def test_fred_dot_is_missing_and_bad_schema_rejected(self):
        rates=parse_fred(b'observation_date,DGS10\n2026-10-29,4.1\n2026-10-30,.\n')
        self.assertIsNone(rates['2026-10-30'])
        with self.assertRaises(PortfolioError):parse_fred(b'Date,Wrong\n2026-10-30,4\n')
