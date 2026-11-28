"""Explain pipeline success separately from score freshness in Actions Summary."""
import json
import os
import sys
from pathlib import Path


def render(summary):
    lines = ['### Collection and score freshness', '',
             '| Market | Collection status | Expected observation | Last valid score | Late sources |',
             '| --- | --- | --- | --- | --- |']
    for market, item in summary.get('markets', {}).items():
        due = item.get('expected_date')
        late = ', '.join(f'{name}: {day or "missing"}' for name, day in item.get('series', {}).items()
                         if not day or (due and day < due)) or 'none'
        lines.append(f'| {market} | {item.get("status")} | {due} | {item.get("last_valid_date")} | {late} |')
    if not summary.get('markets'):
        lines.append('Collection did not produce market receipts; inspect the refresh step logs.')
    return '\n'.join(lines) + '\n'


def main():
    try:
        summary = json.loads(Path(sys.argv[1]).read_text())
    except (OSError, ValueError):
        summary = {}
    result = render(summary)
    print(result)
    if target := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(target, 'a') as stream:
            stream.write(result)


if __name__ == '__main__':
    main()
