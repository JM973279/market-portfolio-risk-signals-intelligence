"""Per-market settings for the portfolio engine.

A snapshot names its market in snapshot_meta.json ("market"); absent means "us",
so existing US snapshots behave exactly as before. Each market is analysed on its
own sessions and currency; markets are never mixed in one portfolio.
"""
from __future__ import annotations

PROFILES = {
    'us': {
        'id': 'us', 'title': '포트폴리오 분석', 'currency': 'USD', 'currency_symbol': '$',
        'market_ticker': 'SPY', 'market_label': 'SPY',
        'required': ('SPY', 'IEF', 'GLD'),
        'references': {'equity': 'SPY', 'bond': 'IEF', 'commodity': 'GLD'},
        'factor_columns': {'rate': 'DGS10', 'volatility': 'VIX'},
        'factor_labels': {'market': '시장 (SPY)', 'rate': '금리 (1bp)', 'volatility': '변동성 (1pt)'},
        'default_benchmark': 'spy',
        'benchmarks': {
            'spy': {'name': 'SPY', 'label': 'SPY · 미국 대형주', 'holdings': [{'ticker': 'SPY', 'weight': 100}]},
            'balanced': {'name': '주식·국채 60:40 (SPY·IEF)', 'label': '주식·국채 60:40 · SPY/IEF', 'holdings': [
                {'ticker': 'SPY', 'weight': 60}, {'ticker': 'IEF', 'weight': 40}]},
        },
        'example': [{'ticker': 'AAPL', 'weight': 30}, {'ticker': 'MSFT', 'weight': 30},
                    {'ticker': 'NVDA', 'weight': 20}, {'ticker': 'AMZN', 'weight': 20}],
        'proposed_extra': 'TLT',
        'replay_domestic': False,
    },
    'korea': {
        'id': 'korea', 'title': '한국 포트폴리오 분석', 'currency': 'KRW', 'currency_symbol': '₩',
        'market_ticker': '069500', 'market_label': 'KODEX 200',
        'required': ('069500', '148070', '132030'),
        'references': {'equity': '069500', 'bond': '148070', 'commodity': '132030'},
        'factor_columns': {'rate': 'KTB10Y', 'volatility': 'VKOSPI'},
        'factor_labels': {'market': '시장 (KODEX 200)', 'rate': '국고채 10년 (1bp)', 'volatility': 'VKOSPI (1pt)'},
        'default_benchmark': 'kodex200',
        'benchmarks': {
            'kodex200': {'name': 'KODEX 200', 'label': 'KODEX 200 · 국내 대형주',
                         'holdings': [{'ticker': '069500', 'weight': 100}]},
            'balanced': {'name': '주식·국채 60:40 (KODEX 200·KOSEF 국고채10년)',
                         'label': '주식·국채 60:40 · KODEX 200/국고채10년',
                         'holdings': [{'ticker': '069500', 'weight': 60}, {'ticker': '148070', 'weight': 40}]},
        },
        'example': [{'ticker': '005930', 'weight': 30}, {'ticker': '000660', 'weight': 20},
                    {'ticker': '005380', 'weight': 20}, {'ticker': '035420', 'weight': 15},
                    {'ticker': '105560', 'weight': 15}],
        'proposed_extra': '148070',
        'replay_domestic': True,
    },
}


def profile(meta):
    market = (meta or {}).get('market', 'us')
    if market not in PROFILES:
        raise ValueError(f'unknown market {market!r}')
    return PROFILES[market]


def public(p):
    """Fields the web page needs to label the market."""
    return {k: p[k] for k in ('id', 'title', 'currency', 'currency_symbol', 'market_ticker', 'market_label',
                              'factor_labels', 'default_benchmark', 'proposed_extra', 'replay_domestic')}
