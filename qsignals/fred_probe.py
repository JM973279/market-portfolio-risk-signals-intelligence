"""Cheap Actions-only readiness check; never publish prices or scores."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SERIES = ('DBAA', 'DGS10')


def korea_retry_needed(provenance: Path, now: datetime) -> bool:
    from qsignals.calendar import latest_closed_session
    published = json.loads(provenance.read_text())['last_date']
    date.fromisoformat(published)
    return published < latest_closed_session(now, publication_lag_hours=6)


def observation_dates(text: str, series: str, today: date) -> set[str]:
    rows = csv.DictReader(io.StringIO(text))
    fields = rows.fieldnames or []
    day_key = next((key for key in ('DATE', 'observation_date') if key in fields), None)
    if day_key is None or series not in fields:
        raise ValueError(f'{series}: unexpected CSV schema')
    dates = set()
    for row in rows:
        value = row[series]
        if value in ('', '.'):
            continue
        if not math.isfinite(float(value)):
            raise ValueError(f'{series}: non-finite observation')
        day = date.fromisoformat(row[day_key])
        if day <= today:
            dates.add(day.isoformat())
    return dates


def fetch_dates(series: str, today: date) -> set[str]:
    # Two small, bounded downloads; no model, API secrets or third-party packages.
    query = urllib.parse.urlencode({
        'id': series, 'cosd': (today - timedelta(days=14)).isoformat(),
        'coed': today.isoformat(),
    })
    request = urllib.request.Request(
        f'https://fred.stlouisfed.org/graph/fredgraph.csv?{query}',
        headers={'User-Agent': 'qsignals-readiness/1.0'},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read(256_001)
    if len(payload) > 256_000:
        raise ValueError(f'{series}: response too large')
    return observation_dates(payload.decode('utf-8-sig'), series, today)


def probe(provenance: Path, today: date) -> dict:
    published = json.loads(provenance.read_text())['last_risk_date']
    date.fromisoformat(published)
    observations = {series: fetch_dates(series, today) for series in SERIES}
    # The spread requires observations on the SAME date. Comparing maxima alone
    # can trigger inference even though the two series have no common new date.
    common = observations['DBAA'] & observations['DGS10']
    ready = max(common) if common else None
    return {
        'run_refresh': bool(ready and ready > published),
        'published': published,
        'latest': {key: max(days) if days else None for key, days in observations.items()},
        'common_date': ready,
        'reason': 'new_common_observation' if ready and ready > published else 'no_new_common_observation',
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provenance', type=Path, default=Path('data/input/us_provenance.json'))
    parser.add_argument('--retry-korea', action='store_true', help='Keep the noon Korea retry if its score is late')
    parser.add_argument('--korea-provenance', type=Path, default=Path('data/input/provenance.json'))
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        if args.retry_korea and korea_retry_needed(args.korea_provenance, now):
            result = {'run_refresh': True, 'reason': 'korea_retry_needed'}
        else:
            result = probe(args.provenance, now.date())
    except Exception as exc:
        # Probe failures must be visible, but must not launch an expensive batch
        # blindly. The unconditional morning run retains the normal stale checks.
        result = {'run_refresh': False, 'reason': 'probe_failed', 'error': str(exc)}
        print(f'::warning::FRED readiness check failed: {exc}; retry at the next scheduled check.')
    print(json.dumps(result, ensure_ascii=False))
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a') as stream:
            stream.write(f"run_refresh={str(result['run_refresh']).lower()}\n")
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(summary, 'a') as stream:
            stream.write('### FRED readiness check\n\n```json\n' + json.dumps(result, indent=2) + '\n```\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
