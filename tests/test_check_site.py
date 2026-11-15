"""The site check passes a site that serves exactly this checkout (no network)."""
import io
import json
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from scripts import check_site

ROOT = check_site.ROOT


def faithful_site(base, path, body=None):
    if path.startswith('/data/'):
        return 200, (ROOT / 'frontend/public/data' / path.removeprefix('/data/')).read_bytes()
    for market, (api, folder, currency, _) in check_site.ANALYSES.items():
        if path == api + '/meta':
            end = json.loads((ROOT / folder / 'current.json').read_text())['price_as_of']
            return 200, json.dumps({'coverage': {'end': end}}).encode()
        if path == api + '/analyze':
            return 200, json.dumps({'currency': currency, 'summary': {}}).encode()
    return 200, b'<html></html>'


class CheckSiteTest(unittest.TestCase):
    def test_a_faithful_site_passes_and_reports_score_dates(self):
        with patch.object(check_site, 'fetch', faithful_site):
            problems, dates = check_site.check('http://site')
        self.assertEqual(problems, [])
        self.assertIn('korea_score_due', dates)
        self.assertIn('us_score_due', dates)

    def test_a_stale_preopen_file_is_reported(self):
        def stale(base, path, body=None):
            if path == '/data/korea-preopen.json':
                return 200, b'{}'
            return faithful_site(base, path, body)
        with patch.object(check_site, 'fetch', stale), redirect_stderr(io.StringIO()):
            problems, _ = check_site.check('http://site')
        self.assertEqual(problems, ['korea-preopen.json differs from this checkout'])


if __name__ == '__main__':
    unittest.main()
