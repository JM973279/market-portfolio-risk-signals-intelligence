"""Write a static HTML view of this repo's own data: reports/dashboard.html.

    python3 -m qsignals.view [--days 120]

Reads only what this repo stores: data/input/{korea,us}_scores.csv,
data/input/provenance.json, data/events/kospi_2026_events.csv and
reports/event_diagnostics.csv. Nothing is fetched and the deployed site is not
involved. Standard library only; open the file in a browser.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from html import escape
from pathlib import Path

from qsignals.diagnostics import VERDICTS, WARNING_THRESHOLD
from qsignals.report import RECORD_LABELS
from qsignals.scores import read_scores

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MARKET_NAMES = {"korea": ("한국", "KOSPI200"), "us": ("미국", "SPY")}
STATUS_LABELS = {
    "CURRENT": "최신 관측일 점수 확인",
    "DELAYED": "필수 원천 지연 · 마지막 유효 점수",
    "BLOCKED": "재현 검증 실패 · 이전 import 유지",
    "UNAVAILABLE": "점수 없음",
}


def _pct(x):
    return "–" if x is None else f"{x * 100:.1f}%"


def _num(x, digits=3):
    return "–" if x is None else f"{x:.{digits}f}"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def risk_chart(rows, days):
    """Inline SVG: Risk Score line with the 50% warning line; post-cutoff dates shaded."""
    shown = [r for r in rows if r.risk_v1 is not None][-days:]
    if len(shown) < 2:
        return '<p class="muted">표시할 점수가 부족합니다.</p>'
    w, h, pad_l, pad_b, pad_t = 720, 220, 36, 26, 10
    step = (w - pad_l - 8) / (len(shown) - 1)
    x = lambda i: pad_l + i * step
    y = lambda v: pad_t + (1 - v) * (h - pad_t - pad_b)
    points = " ".join(f"{x(i):.1f},{y(r.risk_v1):.1f}" for i, r in enumerate(shown))
    first_post = next((i for i, r in enumerate(shown) if r.record_type != "OOS_WALK_FORWARD"), None)
    shade = ""
    if first_post is not None:
        x0 = x(first_post) - step / 2
        shade = (f'<rect x="{x0:.1f}" y="{pad_t}" width="{w - 8 - x0:.1f}" height="{h - pad_t - pad_b}" class="post"/>'
                 f'<text x="{x0 + 4:.1f}" y="{pad_t + 12}" class="axis">동결 모델 추론 ({escape(shown[first_post].date)}~)</text>')
    grid = "".join(f'<line x1="{pad_l}" x2="{w - 8}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="gl"/>'
                   f'<text x="{pad_l - 6}" y="{y(v) + 4:.1f}" class="axis" text-anchor="end">{int(v * 100)}</text>'
                   for v in (0, 0.25, 0.5, 0.75, 1))
    last_i = len(shown) - 1
    anchor = lambda i: "start" if i == 0 else "end" if i == last_i else "middle"
    ticks = "".join(f'<text x="{x(i):.1f}" y="{h - 8}" class="axis" text-anchor="{anchor(i)}">{escape(shown[i].date[5:])}</text>'
                    for i in sorted({0, last_i // 3, 2 * last_i // 3, last_i}))
    last = shown[-1]
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Risk Score 최근 {len(shown)}거래일">'
            f'{shade}{grid}<line x1="{pad_l}" x2="{w - 8}" y1="{y(WARNING_THRESHOLD):.1f}" y2="{y(WARNING_THRESHOLD):.1f}" class="warn"/>'
            f'<polyline points="{points}" class="line"/>'
            f'<circle cx="{x(len(shown) - 1):.1f}" cy="{y(last.risk_v1):.1f}" r="3.5" class="dot"/>{ticks}</svg>')


def market_section(market, rows, info, source, days):
    name, equity = MARKET_NAMES[market]
    scored = [r for r in rows if r.risk_v1 is not None]
    last = scored[-1]
    status = (info or {}).get("status")
    expected = (info or {}).get("expected_date")
    badge = STATUS_LABELS.get(status, "상태 기록 없음")
    note = ""
    if status == "DELAYED":
        note = (f'<p class="note">기대 관측일 {escape(expected or "–")}의 필수 원천이 아직 없어 '
                f'{escape(last.date)}까지만 점수가 있습니다. 이 값을 현재 점수로 이월하지 않습니다.</p>')
    counts = {}
    for r in rows:
        counts[r.record_type] = counts.get(r.record_type, 0) + 1
    count_text = " · ".join(f"{RECORD_LABELS.get(k, k)} {v:,}" for k, v in sorted(counts.items()))
    recent = "".join(
        f'<tr><th scope="row">{escape(r.date)}</th><td>{_pct(r.risk_v1)}</td><td>{_num(r.msi)}</td>'
        f'<td>{_num(r.stress_threshold)}</td><td>{escape(RECORD_LABELS.get(r.record_type, r.record_type))}</td></tr>'
        for r in reversed(scored[-8:]))
    return f"""
<section class="card" aria-labelledby="{market}-h">
 <header><h2 id="{market}-h">{name} <small>{equity} · V1</small></h2><span class="badge {escape(status or 'NONE').lower()}">{escape(badge)}</span></header>
 <div class="kpis">
  <div><span>Risk Score (10D) · {escape(last.date)}</span><strong>{_pct(last.risk_v1)}</strong></div>
  <div><span>MSI</span><strong>{_num(last.msi)}</strong></div>
  <div><span>공식 Stress 기준</span><strong>{_num(last.stress_threshold)}</strong></div>
  <div><span>기록 유형</span><strong class="small">{escape(RECORD_LABELS.get(last.record_type, last.record_type))}</strong></div>
 </div>
 {note}
 <figure>{risk_chart(rows, days)}<figcaption>최근 {days}거래일 Risk Score(%) · 점선 = 경보 기준 {int(WARNING_THRESHOLD * 100)}%</figcaption></figure>
 <details><summary>최근 8개 점수</summary><div class="scroll"><table><thead><tr><th>날짜</th><th>Risk</th><th>MSI</th><th>기준</th><th>유형</th></tr></thead><tbody>{recent}</tbody></table></div></details>
 <p class="muted">{escape(count_text)}</p>
 <p class="muted">파일 <code>data/input/{market}_scores.csv</code> · import {escape(source.get("imported_at") or "–")}{" (이전 import 유지)" if source.get("kept_from_previous_import") else ""}<br>
 출처 {escape(source.get("source_repo") or "–")} @ <code>{escape((source.get("source_git_commit") or "–")[:7])}</code> · 수집 실행 <code>{escape(source.get("operational_run_id") or "–")}</code></p>
</section>"""


def diagnostics_section(path):
    if not Path(path).exists():
        return ""
    with Path(path).open(newline="", encoding="utf-8") as f:
        recs = list(csv.DictReader(f))
    def ret(value):
        return f"{float(value):.2f}%" if value else "–"

    def risk(value):
        return _pct(float(value)) if value else "–"

    body = "".join(
        f'<tr><th scope="row">{escape(r["date"])}</th><td>{escape(r["trigger_primary"])}</td>'
        f'<td>{ret(r["kospi200_return_pct"])}</td><td>{risk(r["max_risk_pre"])}</td>'
        f'<td><span class="verdict {escape(r["verdict"].lower())}">{escape(VERDICTS.get(r["verdict"], r["verdict"]))}</span></td></tr>'
        for r in recs)
    return f"""
<section class="card wide" aria-labelledby="diag-h">
 <header><h2 id="diag-h">한국 급락일 사전 경보 진단</h2><span class="badge none">reports/event_diagnostics.csv</span></header>
 <div class="scroll"><table><thead><tr><th>급락일</th><th>트리거</th><th>KOSPI200</th><th>직전 10일 최고 Risk</th><th>판정</th></tr></thead><tbody>{body}</tbody></table></div>
</section>"""


def storage_section(provenance, files):
    refresh = provenance.get("refresh", {})
    rows = "".join(f'<tr><th scope="row"><code>{escape(rel)}</code></th><td>{escape(desc)}</td><td><code>{_sha(PROJECT_ROOT / rel)[:12]}…</code></td></tr>'
                   for rel, desc in files if (PROJECT_ROOT / rel).exists())
    source = f'{escape(provenance.get("source_repo") or "–")} @ <code>{escape((provenance.get("source_git_commit") or "–")[:10])}</code>'
    return f"""
<section class="card wide" aria-labelledby="store-h">
 <header><h2 id="store-h">데이터 저장 방식</h2><span class="badge none">이 저장소 파일만 사용</span></header>
 <p>점수는 이 저장소의 CSV로 저장합니다. 배포 사이트(JSON export + 웹 이미지)와 별도이며, 이 화면은 아래 파일만 읽어 만듭니다. 시장별 출처 커밋·수집 실행은 각 카드 아래에 있습니다.</p>
 <div class="scroll"><table><thead><tr><th>파일</th><th>내용</th><th>SHA-256</th></tr></thead><tbody>{rows}</tbody></table></div>
 <dl>
  <div><dt>한국 점수 import</dt><dd>{escape(provenance.get("imported_at") or "–")}</dd></div>
  <div><dt>한국 수집 실행</dt><dd><code>{escape(provenance.get("operational_run_id") or "–")}</code></dd></div>
  <div><dt>한국 점수 파이프라인</dt><dd>{source} (git archive, 읽기 전용)</dd></div>
  <div><dt>V1 커밋</dt><dd><code>{escape((refresh.get("v1_commit") or "–")[:10])}</code></dd></div>
 </dl>
</section>"""


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16202c;--muted:#5b6675;--line:#e1e5eb;--accent:#2457c5;--warn:#c2410c;--post:rgba(36,87,197,.07);--ok:#13795b;--okbg:#e5f4ee;--delay:#9a5b00;--delaybg:#fdf1dc;--bad:#b42318;--badbg:#fde8e7}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f141a;--card:#171e27;--ink:#e6ebf1;--muted:#9aa6b4;--line:#2a3441;--accent:#7aa2ff;--warn:#fb923c;--post:rgba(122,162,255,.09);--ok:#5fd3a6;--okbg:#123329;--delay:#f5b955;--delaybg:#3a2a0e;--bad:#ff8a80;--badbg:#3b1614}}
:root[data-theme="dark"]{--bg:#0f141a;--card:#171e27;--ink:#e6ebf1;--muted:#9aa6b4;--line:#2a3441;--accent:#7aa2ff;--warn:#fb923c;--post:rgba(122,162,255,.09);--ok:#5fd3a6;--okbg:#123329;--delay:#f5b955;--delaybg:#3a2a0e;--bad:#ff8a80;--badbg:#3b1614}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic",sans-serif}
main{max-width:1120px;margin:0 auto;padding:28px 16px 48px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:0}h2 small{font-weight:500;color:var(--muted);font-size:13px;margin-left:6px}
.lead{color:var(--muted);margin:0 0 22px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;min-width:0}.wide{grid-column:1/-1}
.card header{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.badge{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--bg);color:var(--muted);border:1px solid var(--line)}
.badge.current{background:var(--okbg);color:var(--ok);border-color:transparent}.badge.delayed{background:var(--delaybg);color:var(--delay);border-color:transparent}.badge.blocked,.badge.unavailable{background:var(--badbg);color:var(--bad);border-color:transparent}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:10px}.kpis div{border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.kpis span{display:block;font-size:12px;color:var(--muted)}.kpis strong{font-size:24px;font-variant-numeric:tabular-nums}.kpis strong.small{font-size:15px}
.note{background:var(--delaybg);color:var(--delay);border-radius:8px;padding:8px 12px;font-size:13px;margin:8px 0}
figure{margin:12px 0 4px}figure svg{width:100%;height:auto;display:block}figcaption,.muted{color:var(--muted);font-size:12px}
.line{fill:none;stroke:var(--accent);stroke-width:2}.dot{fill:var(--accent)}.warn{stroke:var(--warn);stroke-dasharray:5 4}.gl{stroke:var(--line)}.post{fill:var(--post)}.axis{fill:var(--muted);font-size:10px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}thead th{color:var(--muted);font-weight:600}
details{margin-top:8px}summary{cursor:pointer;color:var(--accent);font-size:13px}
.verdict{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--bg)}.verdict.missed{background:var(--badbg);color:var(--bad)}.verdict.warned{background:var(--okbg);color:var(--ok)}.verdict.in_stress{background:var(--delaybg);color:var(--delay)}
dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin:12px 0 0}dt{font-size:12px;color:var(--muted)}dd{margin:0;word-break:break-all}code{font-size:12px}
"""


def render(days=120):
    data = PROJECT_ROOT / "data/input"
    provenance = json.loads((data / "provenance.json").read_text(encoding="utf-8"))
    refresh = provenance.get("refresh", {})
    sections = []
    for market in ("korea", "us"):
        path = data / f"{market}_scores.csv"
        if path.exists():
            source = provenance.get("markets", {}).get(market) or (provenance if market == "korea" else {})
            sections.append(market_section(market, read_scores(path, market), refresh.get(market), source, days))
    imported = max((v.get("imported_at") or "" for v in provenance.get("markets", {}).values()),
                   default=provenance.get("imported_at") or "")
    files = [("data/input/korea_scores.csv", "한국 V1 점수·MSI·KOSPI200"),
             ("data/input/us_scores.csv", "미국 V1 점수·MSI·SPY"),
             ("data/input/provenance.json", "출처 커밋·SHA-256·수집 상태"),
             ("data/events/kospi_2026_events.csv", "급락일 주석 (사람이 작성)"),
             ("reports/event_diagnostics.csv", "사전 경보 진단 결과")]
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Qualitative Signals 점수</title><style>{CSS}</style></head>
<body><main>
<h1>Market Qualitative Signals</h1>
<p class="lead">이 저장소에 저장된 V1 점수와 진단 결과 · 마지막 import {escape(imported or "–")} · 정적 파일(실시간 아님)</p>
<div class="grid">{"".join(sections)}{diagnostics_section(PROJECT_ROOT / "reports/event_diagnostics.csv")}{storage_section(provenance, files)}</div>
</main></body></html>
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=120, help="trading days shown in each chart")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "reports/dashboard.html")
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(args.days), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
