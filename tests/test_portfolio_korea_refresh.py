"""Korea collection validation uses synthetic observations, never live provider calls."""
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from qsignals.portfolio_data import PortfolioError, load_dataset, parse_files
from qsignals.portfolio_import import publish
from qsignals.portfolio_korea_refresh import (
    UNIVERSE, build_snapshot, completed_sessions, parse_ecos, parse_vkospi, refresh, request_json)


def fixture():
    days = []
    cursor = date(2022, 1, 3)
    while len(days) < 800:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    quotes = {u[0]: {d: 100 + j + i * .05 + (i % 7) * .01 for i, d in enumerate(days)}
              for j, u in enumerate(UNIVERSE)}
    rates = {d: 3 + (i % 31) * .01 for i, d in enumerate(days)}
    vk = {d: 20 + (i % 17) * .1 for i, d in enumerate(days)}
    return quotes, rates, vk, days


class KoreaRefreshTest(unittest.TestCase):
    def test_prices_and_risk_dates_are_separate_without_filling(self):
        quotes, rates, vk, days = fixture()
        del rates[days[-1]]
        del vk[days[-2]]
        del vk[days[-1]]
        raw, quality = build_snapshot(quotes, rates, vk, days)
        data = parse_files(raw, {})
        self.assertEqual(data.meta['as_of'], days[-1])
        self.assertEqual(data.meta['window_end'], days[-3])
        self.assertEqual(quality['factor_lag_sessions'], 2)
        self.assertIsNone(data.factors[days[-1]]['KTB10Y'])
        self.assertIsNone(data.factors[days[-1]]['VKOSPI'])
        self.assertEqual(data.meta['currency'], 'KRW')

    def test_suspension_stays_missing_without_dropping_krx_sessions(self):
        quotes, rates, vk, days = fixture()
        del quotes['005930'][days[10]]
        raw, quality = build_snapshot(quotes, rates, vk, days)
        data = parse_files(raw, {})
        self.assertEqual(data.days, days)
        self.assertIsNone(data.prices[days[10]]['005930'])
        self.assertEqual(quality['missing_price_dates']['005930'], [days[10]])

    def test_missing_benchmark_latest_price_and_nonfinite_price_block_publication(self):
        for ticker, offset, value in [('069500', 5, None), ('005930', -1, None),
                                      ('005930', 10, float('nan'))]:
            quotes, rates, vk, days = fixture()
            if value is None:
                del quotes[ticker][days[offset]]
            else:
                quotes[ticker][days[offset]] = value
            with self.subTest(ticker=ticker, offset=offset), self.assertRaises(PortfolioError):
                build_snapshot(quotes, rates, vk, days)

    def test_stale_or_insufficient_factors_and_duplicate_sessions_are_rejected(self):
        quotes, rates, vk, days = fixture()
        for d in days[-4:]:
            del rates[d]
        with self.assertRaises(PortfolioError):
            build_snapshot(quotes, rates, vk, days)
        quotes, rates, vk, days = fixture()
        for d in days[100:150]:
            del vk[d]
        with self.assertRaises(PortfolioError):
            build_snapshot(quotes, rates, vk, days)
        quotes, rates, vk, days = fixture()
        with self.assertRaises(PortfolioError):
            build_snapshot(quotes, rates, vk, days + [days[-1]])

    def test_provider_parsers_reject_wrong_index_tenor_and_duplicate_dates(self):
        for raw in [b'Date,Close\n2026-11-10,20\n2026-11-10,21\n',
                    b'Date,Close,Index\n2026-11-10,20,KOSPI\n']:
            with self.assertRaises(PortfolioError):
                parse_vkospi(raw)
        self.assertEqual(parse_vkospi(b'Date,Close\n2026-11-10,20\n'), {'2026-11-10': 20})
        payload = {'StatisticSearch': {'row': [
            {'TIME': '20261110', 'DATA_VALUE': '3.5', 'ITEM_NAME1': '국고채(10년)'}]}}
        self.assertEqual(parse_ecos(payload), {'2026-11-10': 3.5})
        payload['StatisticSearch']['row'][0]['ITEM_NAME1'] = '국고채(3년)'
        with self.assertRaises(PortfolioError):
            parse_ecos(payload)

    def test_krw_provenance_generated_paths_and_receipts_are_verified(self):
        raw, quality = build_snapshot(*fixture())
        with tempfile.TemporaryDirectory() as directory:
            manifest = publish(raw, 'test:github', 'a' * 40, directory,
                collection=quality, receipts={'krx-vkospi.csv': b'Date,Close\n'}, source_paths={})
            self.assertEqual(manifest['currency'], 'KRW')
            self.assertEqual(manifest['market'], 'korea')
            self.assertTrue(all(r['source_path'] is None for r in manifest['files'].values()))
            self.assertEqual(load_dataset(directory).meta['market'], 'korea')
            receipt = manifest['collection']['receipts']['krx-vkospi.csv']
            (Path(directory) / receipt['path']).write_bytes(b'tampered')
            with self.assertRaises(PortfolioError):
                load_dataset(directory)

    def test_failed_refresh_preserves_previous_snapshot_and_rejects_date_regression(self):
        quotes, rates, vk, days = fixture()
        raw, quality = build_snapshot(quotes, rates, vk, days)
        with tempfile.TemporaryDirectory() as directory:
            publish(raw, 'test:github', 'a' * 40, directory, collection=quality, source_paths={})
            current = Path(directory) / 'current.json'
            before = current.read_bytes()
            with patch.dict(os.environ, {'KRX_API_KEY': 'test', 'ECOS_API_KEY': 'test'}), \
                 patch('qsignals.portfolio_korea_refresh.completed_sessions', return_value=days[:-1]), \
                 patch('qsignals.portfolio_korea_refresh.fetch_quotes',
                       return_value={t+'.KS': v for t, v in quotes.items()}), \
                 patch('qsignals.portfolio_korea_refresh.fetch_rates', return_value=rates), \
                 patch('qsignals.portfolio_korea_refresh.fetch_vkospi', return_value=(vk, 'test')):
                with self.assertRaises(PortfolioError):
                    refresh(directory, source_commit='b'*40)
            self.assertEqual(current.read_bytes(), before)

    def test_api_key_is_not_exposed_in_provider_errors(self):
        url = 'https://ecos.example/api/private-key'
        with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError(url, 401, 'Unauthorized', {}, None)):
            with self.assertRaises(PortfolioError) as caught:
                request_json(url)
            self.assertNotIn('private-key', str(caught.exception))

    def test_calendar_waits_until_two_hours_after_korean_close(self):
        before = datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc)
        after = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(completed_sessions(before)[-1], '2026-11-09')
        self.assertEqual(completed_sessions(after)[-1], '2026-11-10')


if __name__ == '__main__':
    unittest.main()
