"""Optional, period-specific sector benchmark adapter.

No current sector weights are backfilled into historical benchmarks. Records are
curated in GitHub, tied to price/benchmark versions, and hash-check raw receipts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from qsignals.portfolio_data import PortfolioError


def load_sector_records(directory):
    root = Path(directory).resolve()
    index = root / 'sector-inputs.json'
    if not index.exists():
        return ()
    try:
        payload = json.loads(index.read_text())
        if payload.get('schema_version') != 1 or not isinstance(payload['records'], list):
            raise ValueError('schema')
        records = []
        for record in payload['records']:
            if record.get('is_example') or not record.get('sources'):
                raise ValueError('Examples and unsourced records are not production inputs')
            for source in record['sources']:
                path = (root / source['path']).resolve()
                if not path.is_relative_to(root) or path == index:
                    raise ValueError('Receipt path must stay inside data directory')
                url = urlsplit(source['url'])
                if url.scheme != 'https' or not url.hostname or url.username or url.password:
                    raise ValueError('Public HTTPS source attribution is required')
                if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
                    raise ValueError('Sector source receipt hash mismatch')
            records.append(record)
        return tuple(records)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        # Optional sector feed failure must not hide valid prices/risk.
        return ({'adapter_error': str(exc)},)


def sector_attribution(data, days, weights, bm):
    from qsignals.portfolio import brinson_fachler
    reason = '과거 벤치마크 섹터 비중·수익률 및 시점별 분류 자료 연결이 필요합니다. 현재 섹터 분류를 과거에 소급 적용하지 않습니다.'
    candidates = [r for r in data.sector_records if r.get('period') == {'start': days[0], 'end': days[-1]}
                  and r.get('benchmark_weights') == bm['weights']
                  and r.get('price_snapshot_sha') == data.provenance.get('source_commit')]
    if len(candidates) != 1:
        if data.sector_records and 'adapter_error' in data.sector_records[0]:
            reason = '섹터 자료 검증 실패: ' + data.sector_records[0]['adapter_error']
        return {'status': 'unavailable', 'reason': reason}
    record = candidates[0]
    try:
        if record.get('currency') != 'USD' or record.get('return_basis') != 'dividend_split_adjusted_close':
            raise PortfolioError('섹터 자료의 통화·수익률 기준이 다릅니다.')
        if record.get('classification_policy') != 'fixed_start_point_in_time' or record.get('classification_as_of') != days[0]:
            raise PortfolioError('시작 시점 분류 자료가 필요합니다.')
        equity = {t: w for t, w in weights.items() if data.universe[t]['asset_class'] == 'equity'}
        equity_weight = sum(equity.values())
        if not equity_weight:
            raise PortfolioError('주식 구간이 없습니다.')
        if any(data.universe[t]['type'] != 'stock' for t in equity):
            raise PortfolioError('ETF의 과거 섹터별 보유내역·수익률 재구성 자료가 필요합니다.')
        groups = {}
        for ticker, w in equity.items():
            key = record['classifications'][ticker]
            weight = w / equity_weight
            ret = data.prices[days[-1]][ticker] / data.prices[days[0]][ticker] - 1
            group = groups.setdefault(key, {'weight': 0.0, 'contribution': 0.0})
            group['weight'] += weight
            group['contribution'] += weight * ret
        portfolio = {k: {'weight': r['weight'], 'return': r['contribution'] / r['weight']} for k, r in groups.items()}
        reference = record['benchmark_groups']
        # For mixed baskets the record must describe the benchmark's equity sleeve,
        # not the full balanced return. Verify it against the exact benchmark prices.
        b_equity = {t: w for t, w in bm['weights'].items() if data.universe[t]['asset_class'] == 'equity'}
        total = sum(b_equity.values())
        if not total:
            raise PortfolioError('비교 기준에 주식 구간이 없습니다.')
        actual_return = sum(w / total * (data.prices[days[-1]][t] / data.prices[days[0]][t] - 1)
                            for t, w in b_equity.items())
        reference_return = sum(r['weight'] * r['return'] for r in reference.values())
        if abs(reference_return - actual_return) > 1e-10:
            raise PortfolioError('섹터 합계가 주식 기준 수익률과 일치하지 않습니다.')
        result = brinson_fachler(portfolio, reference,
                                 off_benchmark_returns=record.get('off_benchmark_returns'))
        result.update(scope='equity_sector', portfolio_equity_start_weight=equity_weight,
                      benchmark_equity_start_weight=total,
                      scope_note='주식 구간을 각각 100%로 환산한 효과입니다. 전체 자산군 효과와 합산하지 않습니다.',
                      sources=record['sources'], classification_policy=record['classification_policy'])
        return result
    except (PortfolioError, KeyError, TypeError, ZeroDivisionError) as exc:
        return {'status': 'unavailable', 'reason': str(exc)}
