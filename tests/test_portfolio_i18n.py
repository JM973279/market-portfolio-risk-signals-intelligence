import ast
import json
import re
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from qsignals.portfolio_i18n import EN, PREFIXES, request_lang, translate
from qsignals.portfolio_server import Handler

ROOT = Path(__file__).resolve().parent.parent
HANGUL = re.compile('[가-힣]')
MODULES = ['portfolio', 'portfolio_data', 'portfolio_import', 'portfolio_replay', 'portfolio_sectors', 'portfolio_server']


def korean_literals(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body
                  and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and HANGUL.search(node.value) and id(node) not in docstrings}


class EnglishTextTest(unittest.TestCase):
    def test_every_korean_message_has_english(self):
        missing = {}
        for name in MODULES:
            for value in korean_literals(ROOT / 'qsignals' / f'{name}.py'):
                if value not in EN and value not in PREFIXES:
                    missing.setdefault(name, []).append(value)
        self.assertEqual(missing, {})

    def test_stored_scenario_text_has_english(self):
        for path in (ROOT / 'data' / 'portfolio' / 'snapshots').glob('*/scenarios.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            texts = [data.get('note', ''), *data.get('methodology', {}).get('limitations', [])]
            for s in data['scenarios']:
                texts += [s.get('definition', ''), s.get('rule', ''), s.get('pnl_method', '')]
            for value in texts:
                if HANGUL.search(value):
                    self.assertIn(value, EN, path)

    def test_english_values_have_no_korean(self):
        for value in [*EN.values(), *PREFIXES.values()]:
            self.assertIsNone(HANGUL.search(value), value)

    def test_translate_only_changes_english_requests(self):
        payload = {'error': '유효한 JSON이 필요합니다.', 'name_ko': '주식시장 급락', 'list': ['채권', 3],
                   'reason': '섹터 자료 검증 실패: KeyError'}
        self.assertEqual(translate(payload, 'ko'), payload)
        self.assertEqual(translate(payload, 'en'), {'error': 'Valid JSON is required.', 'name_ko': '주식시장 급락',
                                                    'list': ['Bonds', 3],
                                                    'reason': 'Sector data validation failed: KeyError'})
        self.assertEqual(request_lang('lang=en'), 'en')
        self.assertEqual(request_lang(''), 'ko')
        self.assertEqual(request_lang('lang=fr'), 'ko')


class EnglishApiTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, data_dir=Path('/nonexistent')))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post(self, query):
        request = urllib.request.Request(self.base + '/api/portfolio/analyze' + query, data=b'[]',
                                         headers={'Content-Type': 'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request)
        return json.loads(ctx.exception.read())

    def test_error_follows_requested_language(self):
        self.assertEqual(self.post('')['error'], 'JSON 객체가 필요합니다.')
        self.assertEqual(self.post('?lang=en')['error'], 'A JSON object is required.')


if __name__ == '__main__':
    unittest.main()
