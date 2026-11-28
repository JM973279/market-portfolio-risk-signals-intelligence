"""Latest collection receipts, independent of immutable score publication provenance."""
from __future__ import annotations
import json
import os
from pathlib import Path


def save_collection_status(operational, output_dir):
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    markets = {}
    for name, block in operational['markets'].items():
        due = block.get('expectedDate')
        series = block.get('series', [])
        markets[name] = {
            'status': block.get('status'), 'expectedDate': due,
            'lastValidDate': (block.get('lastValid') or {}).get('date'),
            'series': series, 'reason': block.get('reason'),
            'lateSources': [s['name'] for s in series if s.get('status') == 'ERROR'
                            or not s.get('observationDate')
                            or (due and s['observationDate'] < due)],
        }
    record = {'schema_version': 1, 'runId': operational['runId'],
              'checkedAt': operational['generatedAt'], 'markets': markets}
    path = root / 'collection_status.json'
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    os.replace(temporary, path)
    return record


def apply_collection_status(saved, market, record):
    """Update availability only; never promote an old score or replace its history."""
    if record['checkedAt'] < saved.get('generatedAt', ''):
        return
    latest = record['markets'].get(market)
    if not latest:
        return
    block = saved['block']
    block['collectionStatus'] = {'checkedAt': record['checkedAt'], **latest}
    if latest['status'] in ('DELAYED', 'BLOCKED', 'UNAVAILABLE'):
        block.update(status=latest['status'], current=None,
                     expectedDate=latest['expectedDate'], series=latest['series'],
                     reason=latest['reason'])
