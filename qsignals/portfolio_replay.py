"""Historical replay: today's weights over past windows, using actual prices.

No betas and no estimation. Each holding keeps its weight from the window start
and moves with its own adjusted close (buy and hold, no rebalancing). Signs follow
the rest of this module: return/P&L positive = gain, negative = loss. Each window
is read on its own; results are never added up.

Windows come from two fixed inputs, never from the portfolio:
- factor_reference: the reference window of each stress scenario
  (data/portfolio/.../scenarios.json), the same dates as the hypothetical shocks.
- korea_library: foreign-driven Korean crash episodes from the scenario library
  (frontend/public/data/korea-scenarios.json). A window starts at the last US
  close before the Korean shock and runs `horizon_days` US sessions. Domestic
  episodes are excluded because the universe has no Korean assets.

Standard library only, like the rest of the portfolio module.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KOREA_LIBRARY_PATH = ROOT / 'frontend' / 'public' / 'data' / 'korea-scenarios.json'
DEFAULT_HORIZON = 10

LIMITATIONS = [
    '현재 비중을 과거 구간 시작일부터 그대로 보유했다고 가정하며, 구간 중 리밸런싱은 반영하지 않습니다.',
    '검증된 스냅샷의 수정종가를 쓰므로 배당은 반영되지만 거래비용·세금·환율은 반영하지 않습니다.',
    '과거 구간에서 실제로 일어난 가격 변화의 재현이며, 미래 손실이나 발생 확률의 예측이 아닙니다.',
    '한국 급락 구간은 한국 충격 직전 미국 종가부터 미국 거래일 기준으로 잽니다. 지원 자산에 한국 자산이 없어 국내발 사례는 제외합니다.',
    '구간이 서로 겹칠 수 있으므로 시나리오별 손익은 합산하지 않습니다.',
]
# Korean assets on KRX sessions: the window starts at the KRX close before the shock
# (the library's reference_date), and domestic episodes are included.
LIMITATIONS_KOREA = [
    LIMITATIONS[0],
    '검증된 스냅샷의 수정종가를 쓰므로 배당은 반영되지만 거래비용·세금은 반영하지 않습니다. 원화 기준입니다.',
    LIMITATIONS[2],
    '한국 급락 구간은 충격 직전 KRX 종가부터 KRX 거래일 기준으로 잽니다. 국내발·해외발 사례를 모두 포함합니다.',
    LIMITATIONS[4],
]


def load_korea_library(path=KOREA_LIBRARY_PATH):
    """Optional input: a missing or malformed export leaves only the factor windows."""
    try:
        library = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if library.get('schema_version') != 1 or not isinstance(library.get('episodes'), list):
        return None
    return library


def build_windows(days, scenarios, korea_library, horizon_days=DEFAULT_HORIZON, domestic_sessions=False):
    """Return (windows, excluded) from the fixed inputs. `days` are the ascending price dates.

    domestic_sessions: `days` are KRX sessions (Korean assets), so domestic episodes are
    kept and a window starts at the reference date itself (the KRX close before onset).
    """
    position = {d: i for i, d in enumerate(days)}
    windows, excluded = [], []
    for s in scenarios['scenarios']:
        start, end = s['reference']['start'], s['reference']['end']
        if start not in position or end not in position or end <= start:
            excluded.append({'id': s['id'], 'name_en': s['name'], 'name_ko': s.get('definition', s['name']),
                             'reason': 'outside_snapshot'})
            continue
        windows.append({'id': s['id'], 'group': 'factor_reference', 'name_en': s['name'],
                        'name_ko': s.get('definition', s['name']), 'start': start, 'end': end,
                        'linked_scenario': s['id'], 'korea': None})
    for e in (korea_library or {}).get('episodes', []):
        names = {'id': e['id'], 'name_en': e['name']['en'], 'name_ko': e['name']['ko']}
        if e.get('geo') == 'domestic' and not domestic_sessions:
            excluded.append({**names, 'reason': 'domestic_source'})
            continue
        metrics = e.get('metrics')
        if not metrics or not metrics.get('reference_date'):
            excluded.append({**names, 'reason': 'no_reference_date'})
            continue
        # The Korean shock starts after the KRX close before onset; the last US close
        # strictly before that date precedes the overnight US session that usually carried it.
        # On KRX sessions the reference date itself is that close.
        before = [d for d in days if (d <= metrics['reference_date'] if domestic_sessions else d < metrics['reference_date'])]
        if not before or position[before[-1]] + horizon_days >= len(days):
            excluded.append({**names, 'reason': 'outside_snapshot'})
            continue
        start = before[-1]
        windows.append({**names, 'group': 'korea_library', 'start': start,
                        'end': days[position[start] + horizon_days], 'linked_scenario': None,
                        'korea': {'onset': e['onset'], 'category': e.get('category'), 'geo': e.get('geo'),
                                  'tier': e.get('tier'),
                                  'kospi200_onset_return': metrics.get('onset_return'),
                                  'kospi200_max_drawdown': metrics.get('max_drawdown')}})
    return windows, excluded


def _round(value, places='0.000001'):
    return float(Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def replay_window(weights, value_usd, prices, days, window, anchor='SPY'):
    """Buy-and-hold path over one window. Returns None if a held asset lacks a price inside it.

    `anchor` is the market reference (SPY, or KODEX 200 for Korea); its return is reported
    under the historical key `spy_return`.
    """
    i, j = days.index(window['start']), days.index(window['end'])
    path = days[i:j + 1]
    tickers = sorted(weights, key=lambda t: (-weights[t], t))
    for day in path:
        for ticker in [*tickers, anchor]:
            price = prices[day].get(ticker)
            if price is None or not math.isfinite(price) or price <= 0:
                return None
    base = prices[path[0]]
    relative = {t: [prices[d][t] / base[t] for d in path] for t in tickers}
    value = [math.fsum(weights[t] * relative[t][k] for t in tickers) for k in range(len(path))]
    worst = min(range(1, len(path)), key=lambda k: value[k])
    by_asset = [{'ticker': t, 'pnl_usd': _round(value_usd * weights[t] * (relative[t][-1] - 1), '0.01')} for t in tickers]
    return {
        'id': window['id'], 'group': window['group'], 'name_en': window['name_en'], 'name_ko': window['name_ko'],
        'start': window['start'], 'end': window['end'], 'sessions': j - i,
        'return': _round(value[-1] - 1), 'pnl_usd': _round(value_usd * (value[-1] - 1), '0.01'), 'by_asset': by_asset,
        'worst_return': _round(value[worst] - 1), 'worst_date': path[worst],
        'spy_return': _round(prices[path[-1]][anchor] / prices[path[0]][anchor] - 1),
        'linked_scenario': window['linked_scenario'], 'korea': window['korea'],
    }


def compute_replay(data, weights, value_usd, korea_path=KOREA_LIBRARY_PATH):
    from qsignals.portfolio_markets import profile
    market = profile(getattr(data, 'meta', None))
    days = data.days
    library = load_korea_library(korea_path)
    horizon = int(data.scenarios.get('horizon_days') or DEFAULT_HORIZON)
    windows, excluded = build_windows(days, data.scenarios, library, horizon, market['replay_domestic'])
    results = []
    for window in windows:
        row = replay_window(weights, value_usd, data.prices, days, window, market['market_ticker'])
        if row is None:
            excluded.append({'id': window['id'], 'name_en': window['name_en'], 'name_ko': window['name_ko'],
                             'reason': 'missing_price'})
        else:
            results.append(row)
    return {
        'methodology': {'approximation': 'historical_replay_buy_and_hold', 'horizon_days': horizon,
                        'scenarios_additive': False, 'is_forecast': False,
                        'limitations': LIMITATIONS_KOREA if market['replay_domestic'] else LIMITATIONS},
        'korea_library_available': library is not None,
        'korea_library_as_of': (library or {}).get('asOf'),
        'results': results,
        'excluded': excluded,
    }
