"""Exercise the deployed two-market HTTP contract, including absent Korea inputs."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from qsignals.portfolio_data import DEFAULT_DATA
from qsignals.portfolio_import import publish
from qsignals.portfolio_server import Handler
from tests.test_portfolio_markets import DAYS, korea_raw


class PortfolioServerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.korea = Path(self.temporary.name) / 'korea'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(
            Handler, data_dir=DEFAULT_DATA, korea_data_dir=self.korea))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def request(self, path, payload=None):
        headers = {'Origin': 'https://site.example', 'X-Forwarded-Host': 'site.example'}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.base + path, headers=headers,
            data=None if payload is None else json.dumps(payload).encode())
        try:
            response = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            body = response.read()
            return response.status, json.loads(body) if 'application/json' in response.headers['Content-Type'] else body

    def test_korea_shell_renders_without_snapshot_and_us_still_works(self):
        status, body = self.request('/portfolio-kr')
        self.assertEqual(status, 200)
        self.assertIn(b'id="data-unavailable"', body)
        status, meta = self.request('/api/portfolio/meta')
        self.assertEqual(status, 200)
        self.assertEqual(meta['market']['id'], 'us')
        self.assertEqual(self.request('/health')[0], 200)

    def test_missing_korea_returns_typed_error_for_get_and_post(self):
        payload = {'holdings': [{'ticker': '005930', 'weight': 100}]}
        for path, body in [('/meta', None), ('/analyze', payload),
                           ('/compare', dict(payload, proposed_holdings=payload['holdings']))]:
            status, result = self.request('/api/portfolio-kr' + path, body)
            self.assertEqual(status, 503)
            self.assertEqual(result['code'], 'data_unavailable')
        status, result = self.request('/api/portfolio-kr/meta?lang=en')
        self.assertEqual(status, 503)
        self.assertEqual(result['error'], 'The verified portfolio inputs cannot be read.')

    def test_korea_analyze_and_compare_use_krw_and_korean_benchmark(self):
        # Synthetic test fixture only; never included in a service image or published data.
        publish(korea_raw(), 'test:fixture', 'a' * 40, self.korea)
        status, meta = self.request('/api/portfolio-kr/meta')
        self.assertEqual(status, 200)
        self.assertEqual(meta['market']['currency'], 'KRW')
        payload = {'holdings': [{'ticker': '005930', 'weight': 100}],
                   'start': DAYS[0], 'end': DAYS[-1], 'initial_value_usd': 10_000_000}
        for path in ('analyze', 'compare'):
            if path == 'compare':
                payload['proposed_holdings'] = [{'ticker': '069500', 'weight': 100}]
            status, result = self.request('/api/portfolio-kr/' + path, payload)
            self.assertEqual(status, 200)
            self.assertEqual(result['currency'], 'KRW')
            self.assertEqual(result['benchmark']['id'], 'kodex200')

    def test_korea_endpoint_rejects_a_us_snapshot(self):
        self.server.RequestHandlerClass = partial(Handler, data_dir=DEFAULT_DATA,
                                                 korea_data_dir=DEFAULT_DATA)
        status, result = self.request('/api/portfolio-kr/meta')
        self.assertEqual(status, 503)
        self.assertEqual(result['code'], 'invalid_data')


if __name__ == '__main__':
    unittest.main()
