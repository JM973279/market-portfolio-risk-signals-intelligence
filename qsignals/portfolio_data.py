"""Read-only, hash-verified portfolio inputs; network access belongs to Actions."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / 'data' / 'portfolio'
FILES = ('prices.csv', 'factors.csv', 'universe.csv', 'snapshot_meta.json', 'scenarios.json')


class PortfolioError(ValueError):
    def __init__(self, message, code='invalid_input', **details):
        super().__init__(message)
        self.code, self.details = code, details


def iso_day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise PortfolioError('날짜는 YYYY-MM-DD 형식이어야 합니다.')
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise PortfolioError('유효하지 않은 날짜입니다.') from exc
    return value


def number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise PortfolioError('유한한 숫자를 입력하세요.')
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise PortfolioError('0보다 큰 유한한 숫자가 필요합니다.' if positive else '유한한 숫자가 필요합니다.')
    return value


def _csv(raw):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise PortfolioError('CSV 열이 없거나 중복됩니다.', 'invalid_data')
    rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise PortfolioError('CSV 열 수가 일치하지 않습니다.', 'invalid_data')
    return reader.fieldnames, rows


def _matrix(raw, required):
    fields, rows = _csv(raw)
    if 'Date' not in fields or not set(required) <= set(fields):
        raise PortfolioError('필수 시계열 열이 없습니다.', 'invalid_data')
    result, previous = {}, ''
    for row in rows:
        day = iso_day(row['Date'])
        if day <= previous or date.fromisoformat(day).weekday() > 4:
            raise PortfolioError('시계열 날짜 순서·중복·거래일을 확인하세요.', 'invalid_data')
        previous = day
        values = {}
        for key in fields:
            if key == 'Date':
                continue
            try:
                value = None if row[key] == '' else float(row[key])
            except ValueError as exc:
                raise PortfolioError('숫자가 아닌 원천 값입니다.', 'invalid_data') from exc
            if value is not None and not math.isfinite(value):
                raise PortfolioError('원천에 NaN 또는 무한값이 있습니다.', 'invalid_data')
            values[key] = value
        result[day] = values
    if len(result) < 2:
        raise PortfolioError('최소 두 관측일이 필요합니다.', 'invalid_data')
    return result


@dataclass(frozen=True)
class Dataset:
    prices: dict
    factors: dict
    universe: dict
    meta: dict
    scenarios: dict
    provenance: dict
    sector_records: tuple = ()

    @property
    def days(self):
        return list(self.prices)


def parse_files(raw, provenance):
    from qsignals.portfolio_markets import profile
    meta, scenarios = (json.loads(raw[n]) for n in ('snapshot_meta.json', 'scenarios.json'))
    try:
        market = profile(meta)
    except ValueError as exc:
        raise PortfolioError('알 수 없는 시장입니다.', 'invalid_data') from exc
    anchor = market['market_ticker']
    _, rows = _csv(raw['universe.csv'])
    universe = {}
    for r in rows:
        if not {'ticker', 'name', 'type', 'sector', 'asset_class'} <= set(r):
            raise PortfolioError('자산 메타데이터 열이 없습니다.', 'invalid_data')
        ticker = r['ticker']
        if not re.fullmatch(r'[A-Z0-9.\-]{1,16}', ticker) or ticker in universe:
            raise PortfolioError('종목 식별자가 잘못되었거나 중복됩니다.', 'invalid_data')
        if r['type'] not in ('stock', 'etf') or r['asset_class'] not in ('equity', 'bond', 'commodity'):
            raise PortfolioError('지원하지 않는 자산 분류입니다.', 'invalid_data')
        universe[ticker] = r
    if not set(market['required']) <= set(universe):
        raise PortfolioError('기준 자산이 필요합니다: ' + '·'.join(market['required']), 'invalid_data')
    prices = _matrix(raw['prices.csv'], universe)
    for day, values in prices.items():
        if values.get(anchor) is None or any(v is not None and v <= 0 for v in values.values()):
            raise PortfolioError('가격은 양수이며 시장 기준 자산 관측이 필요합니다: ' + anchor, 'invalid_data', date=day)
    factors = _matrix(raw['factors.csv'], tuple(market['factor_columns'].values()))
    if iso_day(meta['as_of']) != max(prices) or scenarios['as_of'] != meta.get('scenario_as_of', meta['as_of']):
        raise PortfolioError('가격·시나리오 기준일이 다릅니다.', 'invalid_data')
    for key in ('window_start', 'window_end'):
        iso_day(meta[key])
    if not meta['window_start'] <= meta['window_end'] <= meta['as_of'] or meta.get('scenario_as_of', scenarios['as_of']) > meta['as_of']:
        raise PortfolioError('자료 기준일 순서가 잘못됐습니다.', 'invalid_data')
    for s in scenarios['scenarios']:
        if s['factor'] not in ('market', 'rate', 'volatility'):
            raise PortfolioError('알 수 없는 충격 팩터입니다.', 'invalid_data')
        number(s['shock'])
    return Dataset(prices, factors, universe, meta, scenarios, provenance)


def load_dataset(directory=DEFAULT_DATA):
    directory = Path(directory)
    try:
        manifest = json.loads((directory / 'current.json').read_text(encoding='utf-8'))
        source_sha = manifest['source_commit']
        if not re.fullmatch(r'[a-f0-9]{40}', source_sha):
            raise PortfolioError('잘못된 원본 커밋입니다.', 'invalid_data')
        sha = manifest.get('snapshot_id', source_sha)
        if not re.fullmatch(r'[a-f0-9]{40}', sha):
            raise PortfolioError('잘못된 원본 버전입니다.', 'invalid_data')
        raw = {}
        for name in FILES:
            record = manifest['files'][name]
            if record['path'] != f'snapshots/{sha}/{name}':
                raise PortfolioError('잘못된 스냅샷 경로입니다.', 'invalid_data')
            data = (directory / record['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != record['sha256']:
                raise PortfolioError('입력 파일 해시가 일치하지 않습니다.', 'invalid_data')
            raw[name] = data
        for record in manifest.get('collection', {}).get('receipts', {}).values():
            relative = record['path']
            if not relative.startswith(f'snapshots/{sha}/receipts/') or '/' in relative.split('/receipts/', 1)[1]:
                raise PortfolioError('잘못된 수집 기록 경로입니다.', 'invalid_data')
            if hashlib.sha256((directory / relative).read_bytes()).hexdigest() != record['sha256']:
                raise PortfolioError('수집 기록 해시가 일치하지 않습니다.', 'invalid_data')
        from dataclasses import replace
        from qsignals.portfolio_sectors import load_sector_records
        return replace(parse_files(raw, manifest), sector_records=load_sector_records(directory))
    except (OSError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise PortfolioError('검증된 포트폴리오 입력을 읽을 수 없습니다.', 'data_unavailable') from exc
