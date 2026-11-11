// The backtest view recomputes from stored OOS predictions; it must agree with the stored metrics.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const code = ts.transpileModule(fs.readFileSync('src/lib/backtest.ts', 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const mod = {exports:{}};
vm.runInNewContext(code, {module:mod, exports:mod.exports});
const {forwardLabels, counts, rocAuc, byYear, episodes, stressFlags} = mod.exports;

// Synthetic: label looks only at t+1…t+h, and a missing day makes the label unknown.
const day = i => `2020-01-${String(i + 1).padStart(2, '0')}`;
const pts = [0, 0, 1, 0, 0, null, 0].map((s, i) => ({date:day(i), price:1, risk:i / 10, msi:s === null ? null : s * 2, threshold:s === null ? null : 1}));
assert.deepEqual(stressFlags(pts), [false, false, true, false, false, null, false]);
assert.deepEqual(forwardLabels(pts, 2), [true, true, false, null, null, null, null]);
const c = counts(pts, forwardLabels(pts, 2), .1);
assert.deepEqual([c.tp, c.fp, c.fn, c.tn], [1, 1, 1, 0]);
// Episodes: bursts closer than the gap merge; warning must come before the first stress day.
const ep = Array.from({length:40}, (_, i) => ({date:`2020-${String(Math.floor(i / 28) + 1).padStart(2, '0')}-${String(i % 28 + 1).padStart(2, '0')}`, price:1, risk:i === 3 ? .9 : .1, msi:[5, 7, 30].includes(i) ? 2 : 0, threshold:1}));
const e = episodes(ep, .5, 20, 10);
assert.equal(e.length, 2);
assert.deepEqual([e[0].onset, e[0].stressDays, e[0].verdict, e[0].lead], [ep[5].date, 2, 'warned', 2]);
assert.equal(e[1].verdict, 'missed');

// Real data: the 50% cut-off reproduces the reported US 10D precision, recall, n and AUC.
const g = JSON.parse(fs.readFileSync('public/data/global-markets.json', 'utf8'));
const m = g.usMetrics.find(x => x.horizon === '10D');
const labels = forwardLabels(g.us, 10);
const us = counts(g.us, labels, .5);
assert.equal(us.n, m.n);
assert.ok(Math.abs(us.precision - m.precision) < 1e-9, `precision ${us.precision} vs ${m.precision}`);
assert.ok(Math.abs(us.recall - m.recall) < 1e-9, `recall ${us.recall} vs ${m.recall}`);
assert.ok(Math.abs(us.f1 - m.f1) < 1e-9);
const auc = rocAuc(g.us, labels);
assert.ok(Math.abs(auc - m.auc) < 1e-6, `auc ${auc} vs ${m.auc}`);
assert.equal(byYear(g.us, labels, .5).reduce((a, y) => a + y.n, 0), m.n);
// Korea has no stored label; it uses the same MSI-above-threshold definition.
const kr = counts(g.korea, forwardLabels(g.korea, 10), .5);
assert.ok(kr.n > 2000 && kr.positives > 0);
console.log(`PASS: label window, missing days, episode merge and lead; US 10D n=${us.n} precision/recall/F1/AUC match stored metrics; Korea n=${kr.n}`);
