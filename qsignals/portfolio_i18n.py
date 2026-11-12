"""English text for the portfolio API (`?lang=en`).

Calculations, codes and stored data stay unchanged: the server builds the usual
Korean response and, for English requests, swaps each known Korean string for its
English version just before sending it. Every Korean literal in the portfolio
modules must have an entry here (tests/test_portfolio_i18n.py checks this).
"""
from __future__ import annotations

EN = {
    # portfolio_server.py
    '한국 포트폴리오 입력이 필요합니다.': 'Korean portfolio inputs are required.',
    '다른 출처의 요청은 허용하지 않습니다.': 'Requests from other origins are not allowed.',
    'application/json이 필요합니다.': 'Content-Type application/json is required.',
    '요청 크기가 잘못되었거나 너무 큽니다.': 'The request size is invalid or too large.',
    'JSON 객체가 필요합니다.': 'A JSON object is required.',
    '비교 포트폴리오가 필요합니다.': 'A comparison portfolio is required.',
    '유효한 JSON이 필요합니다.': 'Valid JSON is required.',
    '유효하지 않은 숫자 또는 요청입니다.': 'Invalid number or request.',
    '분석 중 오류가 발생했습니다. 검증 자료를 확인하세요.': 'The analysis failed. Check the verified data.',
    # portfolio.py
    '주식': 'Equity',
    '채권': 'Bonds',
    '원자재': 'Commodities',
    '주식·국채 60:40 (SPY·IEF)': 'Stocks/Treasuries 60:40 (SPY/IEF)',
    '자산은 1~10개를 입력하세요.': 'Enter between 1 and 10 assets.',
    '비중 합계가 100%여야 합니다.': 'Weights must add up to 100%.',
    '비교 기준을 선택하세요.': 'Select a benchmark.',
    '사용자 지정 기준 포트폴리오': 'Custom benchmark portfolio',
    '지원하지 않는 비교 기준입니다.': 'Unsupported benchmark.',
    '종료일은 시작일보다 늦어야 합니다.': 'The end date must be after the start date.',
    '검증된 가격 기간 안에서 날짜를 선택하세요.': 'Choose dates within the verified price coverage.',
    '기간 안에 최소 두 가격 관측일이 필요합니다.': 'The period needs at least two price observation dates.',
    '요인 합계가 초과수익과 일치하지 않습니다.': 'The attribution effects do not add up to the active return.',
    '수익 기여도 대사 실패': 'Return contribution reconciliation failed',
    '위험 추정에는 최소 30개 일간 수익률이 필요합니다.': 'Risk estimation needs at least 30 daily returns.',
    '위험 추정 시작 전 가격이 필요합니다.': 'A price before the risk estimation start is required.',
    '분석 기준금액이 너무 큽니다.': 'The initial amount is too large.',
    '종목과 비중을 입력하세요.': 'Enter tickers and weights.',
    '지원 종목·중복·비중을 확인하세요.': 'Check for unsupported tickers, duplicates and weights.',
    '분류별 비중과 수익률이 필요합니다.': 'Weights and returns are required for each group.',
    '분류별 비중 합계가 1이어야 합니다.': 'Group weights must add up to 1.',
    '과거 가상성과 · 시작 비중으로 매수 후 보유 · 기간 중 리밸런싱·입출금 없음':
        'Hypothetical past performance · buy and hold at starting weights · no rebalancing, deposits or withdrawals',
    '배당·분할 수정종가 · 배당 별도 중복 가산 없음 · USD':
        'Dividend- and split-adjusted closes · dividends not added twice · USD',
    '세금·수수료·환율 미반영 · 실제 계좌성과 또는 미래 예측이 아님':
        'Excludes taxes, fees and FX · not actual account performance or a forecast',
    '성과 기간과 위험 추정 기간은 별도 표시': 'Performance period and risk estimation window are shown separately',
    '선택 기간에 가격 누락이 있습니다. 기간을 조정하세요.': 'Prices are missing in the selected period. Adjust the period.',
    '잘못된 분류 비중 또는 수익률입니다.': 'Invalid group weight or return.',
    '기준 밖 자산군의 참조 수익률이 필요합니다.': 'A reference return is required for asset classes outside the benchmark.',
    # portfolio_data.py
    '날짜는 YYYY-MM-DD 형식이어야 합니다.': 'Dates must use the YYYY-MM-DD format.',
    '유한한 숫자를 입력하세요.': 'Enter a finite number.',
    'CSV 열이 없거나 중복됩니다.': 'CSV columns are missing or duplicated.',
    'CSV 열 수가 일치하지 않습니다.': 'CSV column counts do not match.',
    '필수 시계열 열이 없습니다.': 'Required time-series columns are missing.',
    '최소 두 관측일이 필요합니다.': 'At least two observation dates are required.',
    '기준 자산 SPY·IEF·GLD가 필요합니다.': 'Reference assets SPY, IEF and GLD are required.',
    '가격·시나리오 기준일이 다릅니다.': 'Price and scenario as-of dates differ.',
    '자료 기준일 순서가 잘못됐습니다.': 'Data as-of dates are out of order.',
    '유효하지 않은 날짜입니다.': 'Invalid date.',
    '0보다 큰 유한한 숫자가 필요합니다.': 'A finite number greater than 0 is required.',
    '유한한 숫자가 필요합니다.': 'A finite number is required.',
    '시계열 날짜 순서·중복·거래일을 확인하세요.': 'Check time-series date order, duplicates and trading days.',
    '자산 메타데이터 열이 없습니다.': 'Asset metadata columns are missing.',
    '종목 식별자가 잘못되었거나 중복됩니다.': 'Ticker identifiers are invalid or duplicated.',
    '지원하지 않는 자산 분류입니다.': 'Unsupported asset class.',
    '가격은 양수이며 SPY 관측이 필요합니다.': 'Prices must be positive and SPY must be observed.',
    '알 수 없는 충격 팩터입니다.': 'Unknown shock factor.',
    '알 수 없는 시장입니다.': 'Unknown market.',
    # portfolio_markets.py
    '포트폴리오 분석': 'Portfolio Analysis',
    '한국 포트폴리오 분석': 'Korea Portfolio Analysis',
    '시장 (SPY)': 'Market (SPY)',
    '시장 (KODEX 200)': 'Market (KODEX 200)',
    '금리 (1bp)': 'Rates (1bp)',
    '국고채 10년 (1bp)': 'Korea 10Y govt bond (1bp)',
    '변동성 (1pt)': 'Volatility (1pt)',
    'SPY · 미국 대형주': 'SPY · US large caps',
    'KODEX 200 · 국내 대형주': 'KODEX 200 · Korean large caps',
    '주식·국채 60:40 · SPY/IEF': 'Stocks/Treasuries 60:40 · SPY/IEF',
    '주식·국채 60:40 (KODEX 200·KOSEF 국고채10년)': 'Stocks/govt bonds 60:40 (KODEX 200/KOSEF 10Y KTB)',
    '주식·국채 60:40 · KODEX 200/국고채10년': 'Stocks/govt bonds 60:40 · KODEX 200/10Y KTB',
    '잘못된 원본 커밋입니다.': 'Invalid source commit.',
    '잘못된 원본 버전입니다.': 'Invalid source version.',
    '검증된 포트폴리오 입력을 읽을 수 없습니다.': 'The verified portfolio inputs cannot be read.',
    '원천에 NaN 또는 무한값이 있습니다.': 'The source contains NaN or infinite values.',
    '잘못된 스냅샷 경로입니다.': 'Invalid snapshot path.',
    '입력 파일 해시가 일치하지 않습니다.': 'Input file hash does not match.',
    '잘못된 수집 기록 경로입니다.': 'Invalid collection receipt path.',
    '수집 기록 해시가 일치하지 않습니다.': 'Collection receipt hash does not match.',
    '숫자가 아닌 원천 값입니다.': 'Non-numeric source value.',
    # portfolio_sectors.py
    '과거 벤치마크 섹터 비중·수익률 및 시점별 분류 자료 연결이 필요합니다. 현재 섹터 분류를 과거에 소급 적용하지 않습니다.':
        'Historical benchmark sector weights, returns and point-in-time classifications must be connected. '
        'Current sector classifications are not applied retroactively.',
    '섹터 자료의 통화·수익률 기준이 다릅니다.': 'Sector data use a different currency or return basis.',
    '시작 시점 분류 자료가 필요합니다.': 'Classification data as of the start date are required.',
    '주식 구간이 없습니다.': 'There is no equity sleeve.',
    'ETF의 과거 섹터별 보유내역·수익률 재구성 자료가 필요합니다.':
        'Historical sector holdings and returns for ETFs must be reconstructed first.',
    '비교 기준에 주식 구간이 없습니다.': 'The benchmark has no equity sleeve.',
    '섹터 합계가 주식 기준 수익률과 일치하지 않습니다.': 'Sector totals do not match the equity benchmark return.',
    '주식 구간을 각각 100%로 환산한 효과입니다. 전체 자산군 효과와 합산하지 않습니다.':
        'Effects with each equity sleeve rescaled to 100%. Do not add them to the asset-class effects.',
    # scripts/build_korea_portfolio.py (local Korean snapshot: asset names, sectors, scenarios, provenance)
    '삼성전자': 'Samsung Electronics',
    'SK하이닉스': 'SK hynix',
    '현대차': 'Hyundai Motor',
    '기아': 'Kia',
    '현대모비스': 'Hyundai Mobis',
    '카카오': 'Kakao',
    'LG화학': 'LG Chem',
    '삼성SDI': 'Samsung SDI',
    '셀트리온': 'Celltrion',
    '삼성바이오로직스': 'Samsung Biologics',
    'KB금융': 'KB Financial Group',
    '신한지주': 'Shinhan Financial Group',
    'POSCO홀딩스': 'POSCO Holdings',
    'LG전자': 'LG Electronics',
    'SK텔레콤': 'SK Telecom',
    'KODEX 코스닥150': 'KODEX KOSDAQ 150',
    'TIGER 미국나스닥100': 'TIGER US NASDAQ 100',
    'KOSEF 국고채10년': 'KOSEF 10Y KTB',
    'KODEX 국고채3년': 'KODEX 3Y KTB',
    'KODEX 골드선물(H)': 'KODEX Gold Futures (H)',
    '반도체': 'Semiconductors',
    '자동차': 'Autos',
    '인터넷': 'Internet',
    '화학·2차전지': 'Chemicals & batteries',
    '바이오': 'Biotech',
    '금융': 'Financials',
    '철강': 'Steel',
    '전자': 'Electronics',
    '통신': 'Telecom',
    '필수소비재': 'Consumer Staples',
    '국내 대형주 지수': 'Korean large-cap index',
    '국내 중소형주 지수': 'Korean small/mid-cap index',
    '해외주식 (원화)': 'Overseas equity (KRW)',
    '국고채 10년': 'Korea 10Y govt bond',
    '국고채 3년': 'Korea 3Y govt bond',
    '금 (환헤지)': 'Gold (FX-hedged)',
    '국내 주식시장 급락': 'Korean equity sell-off',
    '스냅샷 기간 중 KODEX 200 10거래일 수익률의 최저값': 'Lowest 10-session KODEX 200 return in the snapshot period',
    '국고채 10년 금리 급등': 'Korea 10Y govt bond yield spike',
    '스냅샷 기간 중 국고채 10년 10거래일 변화(bp)의 최고값': 'Largest 10-session change (bp) in the Korea 10Y govt bond yield in the snapshot period',
    'VKOSPI 급등': 'VKOSPI spike',
    '스냅샷 기간 중 VKOSPI 10거래일 변화(pt)의 최고값': 'Largest 10-session VKOSPI change (pt) in the snapshot period',
    'Bank of Korea ECOS 817Y002 국고채(10년), %': 'Bank of Korea ECOS 817Y002 10Y govt bond, %',
    'ECOS 국고채(10년)': 'ECOS 10Y govt bond',
    'ECOS_API_KEY 없음': 'ECOS_API_KEY not set',
    'ECOS 817Y002/010210000 is not 국고채(10년)': 'ECOS 817Y002/010210000 is not the 10Y govt bond',
    '한국 섹터 벤치마크 자료가 연결되지 않았습니다.': 'Korean sector benchmark data is not connected.',
    '10년': '10Y',
    # portfolio_replay.py
    '검증된 스냅샷의 수정종가를 쓰므로 배당은 반영되지만 거래비용·세금은 반영하지 않습니다. 원화 기준입니다.':
        'Uses adjusted closes from the verified snapshot, so dividends are included but trading costs and taxes are not. In KRW.',
    '한국 급락 구간은 충격 직전 KRX 종가부터 KRX 거래일 기준으로 잽니다. 국내발·해외발 사례를 모두 포함합니다.':
        'Korean sell-off windows are measured in KRX sessions from the KRX close before the shock. Includes both domestic and foreign-source episodes.',
    '현재 비중을 과거 구간 시작일부터 그대로 보유했다고 가정하며, 구간 중 리밸런싱은 반영하지 않습니다.':
        'Assumes the current weights were held unchanged from the start of each past window; no rebalancing within the window.',
    '검증된 스냅샷의 수정종가를 쓰므로 배당은 반영되지만 거래비용·세금·환율은 반영하지 않습니다.':
        'Uses adjusted closes from the verified snapshot, so dividends are included; trading costs, taxes and FX are not.',
    '과거 구간에서 실제로 일어난 가격 변화의 재현이며, 미래 손실이나 발생 확률의 예측이 아닙니다.':
        'A replay of actual past price moves, not a forecast of future losses or their likelihood.',
    '한국 급락 구간은 한국 충격 직전 미국 종가부터 미국 거래일 기준으로 잽니다. 지원 자산에 한국 자산이 없어 국내발 사례는 제외합니다.':
        'Korea drawdown windows are measured in US sessions from the last US close before the Korean shock. '
        'Domestic-source episodes are excluded because no Korean assets are supported.',
    '구간이 서로 겹칠 수 있으므로 시나리오별 손익은 합산하지 않습니다.':
        'Windows can overlap, so do not add P&L across scenarios.',
    # portfolio_import.py
    '필수 입력 파일 또는 고정 커밋이 없습니다.': 'Required input files or the pinned commit are missing.',
    '과거 벤치마크 섹터 구성·수익률 및 시점별 분류 자료가 연결되지 않았습니다.':
        'Historical benchmark sector composition, returns and point-in-time classifications are not connected.',
    'owner/repository 형식이 필요합니다.': 'Use the owner/repository format.',
    '원본 커밋을 확인할 수 없습니다.': 'The source commit cannot be verified.',
    '같은 원본 커밋의 내용이 달라졌습니다.': 'Content changed for the same source commit.',
    '기존 버전 파일 덮어쓰기를 거부했습니다.': 'Refused to overwrite an existing version file.',
    # Stored scenario definitions (data/portfolio/snapshots/*/scenarios.json)
    '주식시장 급락': 'Equity sell-off',
    '10년 국채금리 급등': '10-year Treasury yield spike',
    '시장 변동성 급등': 'Market volatility spike',
    '스냅샷 기간 중 SPY 10거래일 수익률의 최저값': 'Lowest 10-session SPY return in the snapshot period',
    '스냅샷 기간 중 DGS10 10거래일 변화(bp)의 최고값': 'Largest 10-session DGS10 change (bp) in the snapshot period',
    '스냅샷 기간 중 VIX 10거래일 변화(pt)의 최고값': 'Largest 10-session VIX change (pt) in the snapshot period',
    '손실률(%) = -포트폴리오 Market 베타 × 충격 × 100 (양수=손실, 음수=이익)':
        'Loss (%) = -portfolio market beta × shock × 100 (positive = loss, negative = gain)',
    '손실률(%) = -포트폴리오 Rate 베타(bp당) × 충격 × 100 (양수=손실, 음수=이익)':
        'Loss (%) = -portfolio rate beta (per bp) × shock × 100 (positive = loss, negative = gain)',
    '손실률(%) = -포트폴리오 Volatility 베타(pt당) × 충격 × 100 (양수=손실, 음수=이익)':
        'Loss (%) = -portfolio volatility beta (per pt) × shock × 100 (positive = loss, negative = gain)',
    '사전에 정한 충격 가정에 따른 추정치이며 미래 손실 예측이 아닙니다.':
        'Estimates under predefined shock assumptions, not forecasts of future losses.',
    '각 베타는 팩터를 하나씩 따로 회귀한 민감도이며, 다른 팩터의 영향을 통제한 순수 효과가 아닙니다.':
        'Each beta comes from a separate single-factor regression; it does not control for other factors.',
    '팩터 간 상관으로 같은 시장 움직임이 중복 반영될 수 있으므로 시나리오별 손실은 합산하지 않습니다.':
        'Factors are correlated and can count the same market move twice, so do not add losses across scenarios.',
    '일별 베타에 10거래일 충격을 곱한 선형 근사이며, 미래 손실이나 발생 확률의 예측이 아닙니다.':
        'A linear approximation of daily beta × 10-session shock, not a forecast of future losses or their likelihood.',
}

# Messages built from a fixed Korean prefix plus a technical detail.
PREFIXES = {
    '섹터 자료 검증 실패: ': 'Sector data validation failed: ',
    '배당·분할 수정종가 · 배당 별도 중복 가산 없음 · ': 'Dividend- and split-adjusted closes · dividends not added twice · ',
    '기준 자산이 필요합니다: ': 'Reference assets are required: ',
    '로컬 수집 (Yahoo 수정종가 · KRX VKOSPI · ECOS 국고채) · 팀 내부 시험용 · ':
        'Local collection (Yahoo adjusted close · KRX VKOSPI · ECOS govt bonds) · team-internal trial · ',
    'ECOS 수집 실패: ': 'ECOS collection failed: ',
    '가격은 양수이며 시장 기준 자산 관측이 필요합니다: ': 'Prices must be positive and the market reference asset must be observed: ',
}

# Keys whose values are the Korean original kept on purpose (the English one sits beside it).
KEEP = {'name_ko'}


def text(value: str, lang: str | None) -> str:
    if lang != 'en':
        return value
    if value in EN:
        return EN[value]
    for prefix, english in PREFIXES.items():
        if value.startswith(prefix):
            return english + value[len(prefix):]
    return value


def translate(payload, lang: str | None):
    """Return a copy of an API payload with known Korean strings in `lang` (only 'en' changes anything)."""
    if lang != 'en':
        return payload
    if isinstance(payload, dict):
        return {k: v if k in KEEP else translate(v, lang) for k, v in payload.items()}
    if isinstance(payload, list):
        return [translate(v, lang) for v in payload]
    if isinstance(payload, str):
        return text(payload, lang)
    return payload


def request_lang(query: str) -> str:
    from urllib.parse import parse_qs
    return 'en' if parse_qs(query).get('lang', [''])[0] == 'en' else 'ko'
