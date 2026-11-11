import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// Exercise the actual config, without changing the current process environment.
const code = ts.transpileModule(fs.readFileSync('next.config.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
function config(env) {
  const exports = {};
  vm.runInNewContext(code, { exports, process: { env }, URL });
  return exports.default;
}
for (const url of [undefined, '', 'http://localhost:8000', 'https://localhost:8000', 'https://api.example/path', 'https://user:password@api.example']) {
  await assert.rejects(() => config({ RENDER: 'true', ...(url === undefined ? {} : { PORTFOLIO_API_INTERNAL_URL: url }) }).rewrites());
}
const target = await config({ RENDER: 'true', PORTFOLIO_API_INTERNAL_URL: 'https://api.example/' }).rewrites();
assert.equal(target[0].destination, 'https://api.example/api/portfolio/:path*');
assert.equal((await config({}).rewrites())[0].destination, 'http://127.0.0.1:8000/api/portfolio/:path*');
console.log('PASS: Render HTTPS origin required; localhost/path/credentials rejected; local fallback retained');
