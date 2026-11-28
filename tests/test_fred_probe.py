import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from qsignals import fred_probe


class FredProbeTest(unittest.TestCase):
    def test_korea_retry_uses_calendar_and_skips_today_before_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'korea.json'
            now = datetime(2026, 11, 25, 7, 7, tzinfo=timezone.utc)
            for published, expected in [('2026-11-23', True), ('2026-11-24', False)]:
                path.write_text(json.dumps({'last_date': published}))
                self.assertEqual(fred_probe.korea_retry_needed(path, now), expected)

    def test_korea_retry_is_not_blocked_by_fred_outage(self):
        with patch.object(fred_probe, 'korea_retry_needed', return_value=True), \
             patch.object(fred_probe, 'probe') as probe, \
             patch.dict(os.environ, {'GITHUB_OUTPUT': '', 'GITHUB_STEP_SUMMARY': ''}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            fred_probe.main(['--retry-korea'])
        probe.assert_not_called()
        self.assertTrue(json.loads(output.getvalue())['run_refresh'])

    def decide(self, baa, treasury):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'provenance.json'
            path.write_text(json.dumps({'last_risk_date': '2026-11-20'}))
            with patch.object(fred_probe, 'fetch_dates', side_effect=[set(baa), set(treasury)]):
                return fred_probe.probe(path, date(2026, 11, 25))

    def test_waits_until_both_series_have_a_common_new_date(self):
        for baa, treasury in [(['2026-11-20'], ['2026-11-20']),
                              (['2026-11-23'], ['2026-11-20']),
                              (['2026-11-23'], ['2026-11-24']), ([], [])]:
            with self.subTest(baa=baa, treasury=treasury):
                self.assertFalse(self.decide(baa, treasury)['run_refresh'])
        result = self.decide(['2026-11-23', '2026-11-24'], ['2026-11-23'])
        self.assertTrue(result['run_refresh'])
        self.assertEqual(result['common_date'], '2026-11-23')

    def test_after_publication_same_rates_no_longer_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'provenance.json'
            path.write_text(json.dumps({'last_risk_date': '2026-11-23'}))
            with patch.object(fred_probe, 'fetch_dates', return_value={'2026-11-23'}):
                self.assertFalse(fred_probe.probe(path, date(2026, 11, 25))['run_refresh'])

    def test_missing_nonfinite_and_future_values(self):
        today = date(2026, 11, 25)
        for header in ('DATE', 'observation_date'):
            csv = f'{header},DBAA\n2026-11-20,6.5\n2026-11-23,.\n2026-11-24,\n2099-01-01,6.5\n'
            self.assertEqual(fred_probe.observation_dates(csv, 'DBAA', today), {'2026-11-20'})
        for csv in ('DATE,DBAA\n2026-11-23,nan\n', '<html>unavailable</html>'):
            with self.assertRaises(ValueError):
                fred_probe.observation_dates(csv, 'DBAA', today)

    def test_failed_probe_skips_batch_and_writes_visible_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, summary = Path(tmp) / 'output', Path(tmp) / 'summary'
            with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary)}), \
                 patch.object(fred_probe, 'probe', side_effect=TimeoutError('provider timeout')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fred_probe.main([]), 0)
            self.assertEqual(output.read_text(), 'run_refresh=false\n')
            self.assertIn('probe_failed', summary.read_text())

    def test_requests_only_recent_window_with_bounded_timeout(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'DATE,DGS10\n2026-11-23,4.92\n'
        with patch.object(fred_probe.urllib.request, 'urlopen', return_value=response) as get:
            self.assertEqual(fred_probe.fetch_dates('DGS10', date(2026, 11, 25)), {'2026-11-23'})
        self.assertIn('cosd=2026-11-11', get.call_args.args[0].full_url)
        self.assertEqual(get.call_args.kwargs['timeout'], 20)
