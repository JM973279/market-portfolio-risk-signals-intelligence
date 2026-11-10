/* Run against python3 -m qsignals.portfolio_server (real API, no mocked prices).
   npm/Playwright are optional development-only tools; Python runtime has no deps. */
const fs = require('fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.PORTFOLIO_URL || 'http://127.0.0.1:3108';
const out = process.env.PORTFOLIO_QA_DIR || '/tmp/mqs-portfolio-browser';
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, bypassCSP: true });
    const errors = [], external = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('request', r => { if (!r.url().startsWith(base)) external.push(r.url()); });
    await page.goto(base + '/portfolio');
    await page.waitForFunction(() => document.querySelector('#status').textContent.startsWith('분석 완료'));
    if (process.env.PORTFOLIO_QA_FONT) {
      const data = fs.readFileSync(process.env.PORTFOLIO_QA_FONT).toString('base64');
      await page.addStyleTag({ content: `@font-face{font-family:QAFont;src:url(data:font/woff2;base64,${data}) format('woff2');font-weight:100 900}body{font-family:QAFont,sans-serif}` });
      await page.evaluate(() => document.fonts.ready);
    }
    const api = await page.request.get(base + '/api/portfolio/meta');
    const meta = await api.json();
    if (!await page.locator('#source-status').innerText().then(s => s.includes(meta.coverage.end))) throw Error('actual price date missing');
    const paths = await page.locator('#performance-chart svg path').count();
    if (paths !== 2) throw Error('portfolio and benchmark chart paths missing');
    await page.getByRole('button', { name: '손익 기여 (USD)', exact: true }).click();
    if (!await page.locator('#contribution-bars').innerText().then(s => s.includes('$'))) throw Error('contribution unit switch');
    await page.getByRole('button', { name: '주식 내 섹터별', exact: true }).click();
    if (!await page.locator('#attribution-result').innerText().then(s => s.includes('자료 연결 필요'))) throw Error('sector must not fabricate history');
    await page.getByRole('button', { name: '자산군별', exact: true }).click();
    if (!await page.locator('#attribution-result').innerText().then(s => s.includes('0.00%p'))) throw Error('all-equity allocation');
    await page.locator('#date-slider').focus();
    await page.keyboard.press('Home');
    const firstDate = await page.locator('#chart-readout').innerText();
    if (!firstDate.includes('0.00%')) throw Error('keyboard date selection');
    await page.getByRole('button', { name: '같은 기간으로 비교', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('#comparison-result svg path').length === 3);
    await page.screenshot({ path: out + '/desktop.png', fullPage: true });
    // Client validation must preserve explicit failed/stale state.
    await page.locator('#holdings input').first().fill('40');
    await page.getByRole('button', { name: '과거 성과·위험 분석', exact: true }).click();
    if (!await page.locator('#error').innerText().then(s => s.includes('100%'))) throw Error('invalid weights accepted');
    await page.getByRole('button', { name: '예시 불러오기', exact: true }).click();
    await page.getByRole('button', { name: '과거 성과·위험 분석', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('#results').classList.contains('stale'));
    // Custom benchmark uses actual server math.
    await page.locator('#benchmark-kind').selectOption('custom');
    await page.getByRole('button', { name: '과거 성과·위험 분석', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#benchmark-label').textContent.includes('사용자 지정'));
    if (!await page.locator('#attribution-result').innerText().then(s => s.includes('채권'))) throw Error('custom benchmark allocation missing');
    await page.locator('#benchmark-kind').selectOption('spy');
    await page.getByRole('button', { name: '과거 성과·위험 분석', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('#results').classList.contains('stale'));
    await page.setViewportSize({ width: 360, height: 800 });
    await page.screenshot({ path: out + '/mobile.png', fullPage: true });
    const width = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: innerWidth }));
    if (width.content > width.viewport) throw Error('mobile page overflow ' + JSON.stringify(width));
    const invalid = await page.request.post(base + '/api/portfolio/analyze', { data: { holdings: [], initial_value_usd: 100 } });
    if (invalid.status() !== 422) throw Error('API validation status');
    const foreign = await page.request.post(base + '/api/portfolio/analyze', { headers: { Origin: 'https://untrusted.example' }, data: {} });
    if (foreign.status() !== 403) throw Error('cross-origin rejection');
    if (errors.length || external.length) throw Error(JSON.stringify({ errors, external }));
    const receipt = { priceAsOf: meta.coverage.end, sourceCommit: meta.provenance.source_commit,
      desktop: 1440, mobile: width, cases: ['real performance API', 'comparison 3 lines', 'custom benchmark', 'unit switch',
        'keyboard date', 'sector unavailable state', 'invalid weights', 'HTTP validation', 'same-origin check'], errors, external };
    fs.writeFileSync(out + '/checks.json', JSON.stringify(receipt, null, 2));
    console.log(JSON.stringify(receipt));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
