"""Buy-and-hold performance, arithmetic attribution and separate risk estimates.

All returns are decimals. Display percentages are a presentation concern.
No external data requests or model-score mutations occur here.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import fmean

from qsignals.portfolio_data import Dataset, PortfolioError, iso_day, number

BENCHMARKS = {
    'spy': {'name': 'SPY', 'holdings': [{'ticker': 'SPY', 'weight': 100}]},
    'balanced': {'name': '주식·국채 60:40 (SPY·IEF)', 'holdings': [
        {'ticker': 'SPY', 'weight': 60}, {'ticker': 'IEF', 'weight': 40}]},
}
REFERENCES = {'equity': 'SPY', 'bond': 'IEF', 'commodity': 'GLD'}
CLASS_NAMES = {'equity': '주식', 'bond': '채권', 'commodity': '원자재'}
EXAMPLE = [{'ticker': 'AAPL', 'weight': 30}, {'ticker': 'MSFT', 'weight': 30},
           {'ticker': 'NVDA', 'weight': 20}, {'ticker': 'AMZN', 'weight': 20}]


def holdings(value, universe):
    if not isinstance(value, list) or not 1 <= len(value) <= 10:
        raise PortfolioError('자산은 1~10개를 입력하세요.')
    result = {}
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get('ticker'), str):
            raise PortfolioError('종목과 비중을 입력하세요.')
        ticker = item['ticker'].strip().upper()
        weight = number(item.get('weight'), positive=True)
        if ticker not in universe or ticker in result or weight > 100:
            raise PortfolioError('지원 종목·중복·비중을 확인하세요.', ticker=ticker)
        result[ticker] = weight
    total = math.fsum(result.values())
    if abs(total - 100) > .010000001:
        raise PortfolioError('비중 합계가 100%여야 합니다.', weight_total=total)
    return {t: w / total for t, w in sorted(result.items())}


def benchmark(value, universe):
    if value is None:
        value = {'kind': 'spy'}
    if not isinstance(value, dict):
        raise PortfolioError('비교 기준을 선택하세요.')
    kind = value.get('kind', 'spy')
    if kind == 'custom':
        return {'id': kind, 'name': '사용자 지정 기준 포트폴리오',
                'weights': holdings(value.get('holdings'), universe),
                'strategy': 'buy_and_hold'}
    if kind not in BENCHMARKS:
        raise PortfolioError('지원하지 않는 비교 기준입니다.')
    definition = BENCHMARKS[kind]
    return {'id': kind, 'name': definition['name'],
            'weights': holdings(definition['holdings'], universe),
            'strategy': 'buy_and_hold'}


def _check_prices(data, days, tickers):
    for day in days:
        for ticker in tickers:
            value = data.prices[day].get(ticker)
            if value is None or not math.isfinite(value) or value <= 0:
                raise PortfolioError('선택 기간에 가격 누락이 있습니다. 기간을 조정하세요.',
                                     'missing_price', ticker=ticker, date=day)


def _period(data, start, end, tickers):
    start, end = iso_day(start), iso_day(end)
    if start >= end:
        raise PortfolioError('종료일은 시작일보다 늦어야 합니다.')
    available_start, available_end = data.days[0], data.days[-1]
    if start < available_start or end > available_end:
        raise PortfolioError('검증된 가격 기간 안에서 날짜를 선택하세요.', 'outside_coverage',
                             available_start=available_start, available_end=available_end)
    days = [d for d in data.days if start <= d <= end]
    if len(days) < 2:
        raise PortfolioError('기간 안에 최소 두 가격 관측일이 필요합니다.')
    _check_prices(data, days, tickers)
    return days


def _growth(data, days, weights):
    base = data.prices[days[0]]
    return [math.fsum(w * data.prices[d][t] / base[t] for t, w in weights.items()) for d in days]


def _groups(data, days, weights):
    grouped = {}
    for t, w in weights.items():
        cls = data.universe[t]['asset_class']
        r = data.prices[days[-1]][t] / data.prices[days[0]][t] - 1
        g = grouped.setdefault(cls, {'weight': 0.0, 'contribution': 0.0})
        g['weight'] += w
        g['contribution'] += w * r
    return {k: {'weight': g['weight'], 'return': g['contribution'] / g['weight']}
            for k, g in grouped.items()}


def brinson_fachler(portfolio, reference, *, off_benchmark_returns=None):
    """Single-period BF with explicit zero-weight conventions and reconciliation.

    Missing portfolio sleeve: use its benchmark return (selection=interaction=0).
    Missing benchmark sleeve: require a declared group reference, never assume 0%.
    """
    for side in (portfolio, reference):
        if not isinstance(side, dict) or not side:
            raise PortfolioError('분류별 비중과 수익률이 필요합니다.')
        for g in side.values():
            w, r = number(g['weight']), number(g['return'])
            if w < 0 or r < -1:
                raise PortfolioError('잘못된 분류 비중 또는 수익률입니다.')
        if abs(math.fsum(g['weight'] for g in side.values()) - 1) > 1e-10:
            raise PortfolioError('분류별 비중 합계가 1이어야 합니다.')
    rp = math.fsum(g['weight'] * g['return'] for g in portfolio.values())
    rb = math.fsum(g['weight'] * g['return'] for g in reference.values())
    rows = []
    for key in sorted(set(portfolio) | set(reference)):
        pg, bg = portfolio.get(key), reference.get(key)
        wp, wb = pg['weight'] if pg else 0.0, bg['weight'] if bg else 0.0
        if wp == wb == 0:
            continue
        if wb > 0:
            rbg = bg['return']
        else:
            if key not in (off_benchmark_returns or {}):
                raise PortfolioError('기준 밖 자산군의 참조 수익률이 필요합니다.',
                                     'attribution_unavailable', group=key)
            rbg = number(off_benchmark_returns[key])
        rpg = pg['return'] if wp > 0 else rbg
        a = (wp - wb) * (rbg - rb)
        s = wb * (rpg - rbg)
        i = (wp - wb) * (rpg - rbg)
        rows.append({'group': key, 'name': CLASS_NAMES.get(key, key),
                     'portfolio_weight': wp, 'benchmark_weight': wb,
                     'portfolio_return': rpg, 'benchmark_return': rbg,
                     'allocation': a, 'selection': s, 'interaction': i, 'total': a + s + i,
                     'return_convention': 'benchmark_for_unheld' if wp == 0 else
                         'declared_off_benchmark_reference' if wb == 0 else 'observed'})
    totals = {key: math.fsum(r[key] for r in rows) for key in ('allocation', 'selection', 'interaction')}
    residual = math.fsum(totals.values()) - (rp - rb)
    if abs(residual) > 1e-10:
        raise PortfolioError('요인 합계가 초과수익과 일치하지 않습니다.', 'reconciliation_failed')
    return {'status': 'available', 'method': 'brinson_fachler_3way_single_period',
            'portfolio_return': rp, 'benchmark_return': rb, 'active_return': rp - rb,
            **totals, 'by_group': rows, 'residual': residual,
            'zero_weight_convention': 'benchmark_for_unheld; declared_reference_for_off_benchmark'}


def _attribution(data, days, weights, bm):
    p, b = _groups(data, days, weights), _groups(data, days, bm)
    off, declared = {}, []
    for cls in set(p) - set(b):
        ticker = REFERENCES[cls]
        _check_prices(data, days, [ticker])
        off[cls] = data.prices[days[-1]][ticker] / data.prices[days[0]][ticker] - 1
        declared.append({'group': cls, 'ticker': ticker, 'return': off[cls]})
    result = brinson_fachler(p, b, off_benchmark_returns=off)
    result.update(scope='asset_class', off_benchmark_references=declared)
    return result


def _summary(data, days, weights, bm, value):
    growth, bgrowth = _growth(data, days, weights), _growth(data, days, bm['weights'])
    peak, drawdown = 1.0, 0.0
    series = []
    for day, g, b in zip(days, growth, bgrowth):
        peak = max(peak, g)
        dd = g / peak - 1
        drawdown = min(drawdown, dd)
        series.append({'date': day, 'return': g - 1, 'benchmark_return': b - 1,
                       'active_return': g - b, 'value_usd': value * g, 'drawdown': dd})
    by_asset = []
    for t, w in weights.items():
        r = data.prices[days[-1]][t] / data.prices[days[0]][t] - 1
        by_asset.append({'ticker': t, 'name': data.universe[t]['name'],
                         'classification': data.universe[t]['sector'],
                         'asset_class': data.universe[t]['asset_class'],
                         'start_weight': w, 'return': r, 'contribution': w * r,
                         'pnl_usd': value * w * r})
    by_asset.sort(key=lambda row: (-row['contribution'], row['ticker']))
    total = growth[-1] - 1
    if abs(math.fsum(r['contribution'] for r in by_asset) - total) > 1e-10:
        raise PortfolioError('수익 기여도 대사 실패', 'reconciliation_failed')
    try:
        attr = _attribution(data, days, weights, bm['weights'])
    except PortfolioError as exc:
        attr = {'status': 'unavailable', 'reason': str(exc), 'code': exc.code, 'details': exc.details}
    from qsignals.portfolio_sectors import sector_attribution
    sector = sector_attribution(data, days, weights, bm)
    return {'summary': {'return': total, 'pnl_usd': value * total, 'end_value_usd': value * growth[-1],
                        'benchmark_return': bgrowth[-1] - 1, 'active_return': growth[-1] - bgrowth[-1],
                        'max_drawdown': drawdown},
            'series': series, 'by_asset': by_asset,
            'attribution': {'asset_class': attr, 'equity_sector': sector}}


def _cov(a, b):
    ma, mb = fmean(a), fmean(b)
    return math.fsum((x - ma) * (y - mb) for x, y in zip(a, b)) / (len(a) - 1)


def _regression(y, x):
    if len(x) < 30:
        return None
    vx = _cov(x, x)
    if vx <= 0:
        return None
    beta = _cov(x, y) / vx
    intercept = fmean(y) - beta * fmean(x)
    sse = math.fsum((a - intercept - beta * b) ** 2 for a, b in zip(y, x))
    se = math.sqrt(sse / (len(x) - 2) / ((len(x) - 1) * vx))
    t = beta / se if se > 1e-15 else None
    return {'beta': beta, 't_stat': t, 'significant': abs(t) >= 2 if t is not None else abs(beta) > 1e-12,
            'observations': len(x)}


def risk_analysis(data, weights, value):
    days = [d for d in data.days if data.meta['window_start'] <= d <= data.meta['window_end']]
    if len(days) < 31:
        raise PortfolioError('위험 추정에는 최소 30개 일간 수익률이 필요합니다.', 'risk_unavailable')
    prior = [d for d in data.days if d < days[0]]
    if not prior:
        raise PortfolioError('위험 추정 시작 전 가격이 필요합니다.', 'risk_unavailable')
    source_days = [prior[-1], *days]
    _check_prices(data, source_days, set(weights) | {'SPY'})
    tickers = list(weights)
    returns = {t: [data.prices[d][t] / data.prices[p][t] - 1
                   for p, d in zip(source_days, source_days[1:])] for t in tickers}
    portfolio_returns = [math.fsum(weights[t] * returns[t][i] for t in tickers) for i in range(len(days))]
    variance = max(0.0, _cov(portfolio_returns, portfolio_returns))
    corr = [[(_cov(returns[a], returns[b]) / math.sqrt(_cov(returns[a], returns[a]) * _cov(returns[b], returns[b])))
             if _cov(returns[a], returns[a]) * _cov(returns[b], returns[b]) > 0 else None
             for b in tickers] for a in tickers]
    exposures, asset_exposures = {}, {t: {} for t in tickers}
    for factor in ('market', 'rate', 'volatility'):
        x, ys, yport = [], {t: [] for t in tickers}, []
        for index, (previous, day) in enumerate(zip(source_days, source_days[1:])):
            if factor == 'market':
                change = data.prices[day]['SPY'] / data.prices[previous]['SPY'] - 1
            else:
                column = 'DGS10' if factor == 'rate' else 'VIX'
                before, after = data.factors.get(previous, {}).get(column), data.factors.get(day, {}).get(column)
                if before is None or after is None:
                    continue
                change = (after - before) * (100 if factor == 'rate' else 1)
            x.append(change)
            yport.append(portfolio_returns[index])
            for t in tickers:
                ys[t].append(returns[t][index])
        exposures[factor] = _regression(yport, x)
        for t in tickers:
            asset_exposures[t][factor] = _regression(ys[t], x)
    stress = []
    for scenario in data.scenarios['scenarios']:
        f = scenario['factor']
        if any(asset_exposures[t][f] is None for t in tickers):
            continue
        by_asset = [{'ticker': t, 'pnl_usd': value * weights[t] * asset_exposures[t][f]['beta'] * scenario['shock']}
                    for t in tickers]
        stress.append({**scenario, 'pnl_usd': math.fsum(a['pnl_usd'] for a in by_asset), 'by_asset': by_asset,
                       'significant': exposures[f]['significant']})
    return {'status': 'available', 'window': {'start': days[0], 'end': days[-1], 'observations': len(days)},
            'volatility': math.sqrt(variance * 252),
            'risk_contribution': [{'ticker': t, 'weight': weights[t],
                'share': weights[t] * _cov(returns[t], portfolio_returns) / variance if variance > 1e-20 else None}
                for t in tickers], 'correlation': {'tickers': tickers, 'matrix': corr},
            'factor_exposure': exposures, 'asset_exposure': asset_exposures, 'stress': stress,
            'stress_value_usd': value, 'methodology': 'separate_univariate_daily; no factor controls; scenarios not additive; not a forecast'}


def analyze(data: Dataset, request):
    if not isinstance(request, dict):
        raise PortfolioError('JSON 객체가 필요합니다.')
    w = holdings(request.get('holdings'), data.universe)
    amount = number(request.get('initial_value_usd'), positive=True)
    if amount > 1e15:
        raise PortfolioError('분석 기준금액이 너무 큽니다.')
    bm = benchmark(request.get('benchmark'), data.universe)
    end = request.get('end', data.days[-1])
    start = request.get('start', max(data.days[0], (date.fromisoformat(data.days[-1]) - timedelta(days=365)).isoformat()))
    proposed = holdings(request['proposed_holdings'], data.universe) if 'proposed_holdings' in request else None
    tickers = set(w) | set(bm['weights']) | (set(proposed) if proposed else set())
    days = _period(data, start, end, tickers)
    result = _summary(data, days, w, bm, amount)
    try:
        risk = risk_analysis(data, w, amount)
    except PortfolioError as exc:
        risk = {'status': 'unavailable', 'reason': str(exc), 'code': exc.code}
    result.update(holdings=[{'ticker': t, 'weight': weight * 100} for t, weight in w.items()],
                  initial_value_usd=amount, benchmark=bm, risk=risk,
                  requested_period={'start': start, 'end': end},
                  effective_period={'start': days[0], 'end': days[-1], 'observations': len(days)},
                  provenance=data.provenance,
                  assumptions=['과거 가상성과 · 시작 비중으로 매수 후 보유 · 기간 중 리밸런싱·입출금 없음',
                               '배당·분할 수정종가 · 배당 별도 중복 가산 없음 · USD',
                               '세금·수수료·환율 미반영 · 실제 계좌성과 또는 미래 예측이 아님',
                               '성과 기간과 위험 추정 기간은 별도 표시'])
    if proposed is not None:
        other = _summary(data, days, proposed, bm, amount)
        try:
            other['risk'] = risk_analysis(data, proposed, amount)
        except PortfolioError as exc:
            other['risk'] = {'status': 'unavailable', 'reason': str(exc)}
        result['comparison'] = {'proposed': other,
            'differences': {key: other['summary'][key] - result['summary'][key] for key in result['summary']},
            'same_period': True, 'same_benchmark': True}
    return result


def describe(data):
    return {'assets': list(data.universe.values()), 'benchmarks': BENCHMARKS, 'example': EXAMPLE,
            'coverage': {'start': data.days[0], 'end': data.days[-1]},
            'risk_window': {'start': data.meta['window_start'], 'end': data.meta['window_end']},
            'provenance': data.provenance, 'sector_attribution': data.provenance.get('sector_attribution')}
