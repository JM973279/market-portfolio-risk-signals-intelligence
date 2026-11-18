"""Interrupted live responses retry without accepting incomplete pages or data."""
import contextlib
import http.client
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import check_site


class SiteCheckTest(unittest.TestCase):
    def run_check(self, failed_path, failures, attempts=2, mismatch=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public = root / 'frontend/public/data'
            public.mkdir(parents=True)
            operational = json.dumps({'markets': {}}).encode()
            (public / 'operational-markets.json').write_bytes(operational)
            (public / 'korea-preopen.json').write_bytes(b'{}')
            portfolio = root / 'data/portfolio-kr'
            portfolio.mkdir(parents=True)
            (portfolio / 'current.json').write_text(json.dumps({'price_as_of': '2026-11-18'}))
            bodies = {
                '/': b'<html>complete</html>',
                '/data/operational-markets.json': b'{}' if mismatch else operational,
                '/data/korea-preopen.json': b'{}',
                '/api/portfolio-kr/meta': json.dumps({'coverage': {'end': '2026-11-18'}}).encode(),
                '/api/portfolio-kr/analyze': json.dumps({'currency': 'KRW', 'summary': {}}).encode(),
            }
            failed_requests = 0

            def urlopen(request, **kwargs):
                nonlocal failed_requests
                path = request.full_url.removeprefix('https://example.invalid')
                response = MagicMock()
                response.__enter__.return_value = response
                response.status = 200
                if path == failed_path and failed_requests < failures:
                    failed_requests += 1
                    response.read.side_effect = http.client.IncompleteRead(b'partial', 100)
                else:
                    response.read.return_value = bodies[path]
                return response

            output = io.StringIO()
            with patch.object(check_site, 'ROOT', root), \
                 patch.object(check_site, 'PAGES', ['/']), \
                 patch.object(check_site, 'ANALYSES', {'korea': check_site.ANALYSES['korea']}), \
                 patch.object(check_site.urllib.request, 'urlopen', side_effect=urlopen), \
                 patch.object(check_site.time, 'sleep') as sleep, \
                 patch.object(sys, 'argv', ['check_site', 'https://example.invalid', '--retries', str(attempts)]), \
                 contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                code = check_site.main()
            return code, output.getvalue(), sleep.call_count

    def test_interrupted_page_static_data_and_api_retry_and_recover(self):
        for path in ('/', '/data/operational-markets.json', '/api/portfolio-kr/meta',
                     '/api/portfolio-kr/analyze'):
            with self.subTest(path=path):
                code, output, sleeps = self.run_check(path, failures=1)
                self.assertEqual(code, 0)
                self.assertIn('attempt 1/2:', output)
                self.assertIn('https://example.invalid' + path + ': IncompleteRead', output)
                self.assertIn('site check passed', output)
                self.assertEqual(sleeps, 1)

    def test_persistent_interruption_exhausts_retries_and_fails(self):
        code, output, sleeps = self.run_check('/', failures=10)
        self.assertEqual(code, 1)
        self.assertIn('attempt 2/2:', output)
        self.assertNotIn('site check passed', output)
        self.assertEqual(sleeps, 1)

    def test_data_mismatch_still_fails_after_transport_recovers(self):
        code, output, _ = self.run_check('/', failures=1, mismatch=True)
        self.assertEqual(code, 1)
        self.assertIn('operational-markets.json differs from this checkout', output)
        self.assertNotIn('site check passed', output)
