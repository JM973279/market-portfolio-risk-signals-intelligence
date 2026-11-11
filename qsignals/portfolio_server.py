"""Local read-only portfolio web/API. Run: python3 -m qsignals.portfolio_server"""
from __future__ import annotations

import argparse
import json
import logging
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from qsignals.portfolio import analyze, describe
from qsignals.portfolio_data import DEFAULT_DATA, PortfolioError, load_dataset

WEB = Path(__file__).resolve().parent / 'portfolio_web'
STATIC = {'/portfolio': ('index.html', 'text/html; charset=utf-8'),
          '/portfolio/': ('index.html', 'text/html; charset=utf-8'),
          '/portfolio/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/portfolio/style.css': ('style.css', 'text/css; charset=utf-8')}
LOG = logging.getLogger(__name__)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, data_dir=DEFAULT_DATA, **kwargs):
        self.data_dir = data_dir
        super().__init__(*args, **kwargs)

    def respond(self, code, content, kind='application/json; charset=utf-8'):
        if not isinstance(content, bytes):
            content = json.dumps(content, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/', '/portfolio', '/portfolio/'):
            filename, kind = STATIC['/portfolio']
            self.respond(200, (WEB / filename).read_bytes(), kind)
        elif path in STATIC:
            filename, kind = STATIC[path]
            self.respond(200, (WEB / filename).read_bytes(), kind)
        elif path in ('/api/portfolio/meta', '/health'):
            try:
                data = load_dataset(self.data_dir)
                self.respond(200, describe(data) if path.endswith('/meta') else {
                    'status': 'ok', 'price_as_of': data.meta['as_of'],
                    'source_commit': data.provenance['source_commit']})
            except PortfolioError as exc:
                self.respond(503, {'error': str(exc), 'code': exc.code})
        else:
            self.respond(404, {'error': 'Not found'})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/api/portfolio/analyze', '/api/portfolio/compare'):
            self.respond(404, {'error': 'Not found'})
            return
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            self.respond(403, {'error': '다른 출처의 요청은 허용하지 않습니다.'})
            return
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            self.respond(415, {'error': 'application/json이 필요합니다.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 0 < length <= 32768 or self.headers.get('Transfer-Encoding'):
            self.respond(413, {'error': '요청 크기가 잘못되었거나 너무 큽니다.'})
            return
        try:
            payload = json.loads(self.rfile.read(length), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            if not isinstance(payload, dict):
                raise PortfolioError('JSON 객체가 필요합니다.')
            if path.endswith('/compare') and 'proposed_holdings' not in payload:
                raise PortfolioError('비교 포트폴리오가 필요합니다.')
            data = load_dataset(self.data_dir)
            result = analyze(data, payload)
            self.respond(200, result)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.respond(400, {'error': '유효한 JSON이 필요합니다.'})
        except PortfolioError as exc:
            self.respond(503 if exc.code in ('data_unavailable', 'invalid_data') else 422,
                         {'error': str(exc), 'code': exc.code, 'details': exc.details})
        except ValueError:
            self.respond(400, {'error': '유효하지 않은 숫자 또는 요청입니다.'})
        except Exception:
            LOG.exception('Portfolio request failed')
            self.respond(500, {'error': '분석 중 오류가 발생했습니다. 검증 자료를 확인하세요.'})

    def log_message(self, format, *args):
        LOG.info('%s', format % args)


def serve(host='127.0.0.1', port=3108, data_dir=DEFAULT_DATA):
    server = ThreadingHTTPServer((host, port), partial(Handler, data_dir=data_dir))
    print(f'Portfolio: http://{host}:{server.server_port}/portfolio', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=3108, type=int)
    parser.add_argument('--data-dir', default=DEFAULT_DATA, type=Path)
    args = parser.parse_args()
    serve(args.host, args.port, args.data_dir)


if __name__ == '__main__':
    main()
