"""Pin upstream GitHub exports and publish a validated, replayable snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from qsignals.import_scores import DEFAULT_REPO, _download
from qsignals.portfolio_data import DEFAULT_DATA, FILES, PortfolioError, parse_files


def publish(raw, source_repo, source_commit, output=DEFAULT_DATA, *, collection=None, receipts=None):
    if set(raw) != set(FILES) or not re.fullmatch(r'[a-f0-9]{40}', source_commit):
        raise PortfolioError('필수 입력 파일 또는 고정 커밋이 없습니다.', 'invalid_data')
    snapshot_id = (hashlib.sha256(b''.join(name.encode() + b'\0' + raw[name] for name in sorted(raw))).hexdigest()[:40]
                   if collection else source_commit)
    records = {name: {'path': f'snapshots/{snapshot_id}/{name}',
                      'source_path': f'data/portfolio/{name}' if not collection or name in ('universe.csv', 'scenarios.json') else None,
                      'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
               for name, data in raw.items()}
    manifest = {'schema_version': 1, 'source_repo': source_repo,
                'source_commit': source_commit, 'files': records,
                'imported_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'price_basis': 'dividend_split_adjusted_close', 'currency': 'USD',
                'sector_attribution': {'status': 'unavailable',
                    'reason': '과거 벤치마크 섹터 구성·수익률 및 시점별 분류 자료가 연결되지 않았습니다.'}}
    if collection:
        manifest.update(schema_version=2, snapshot_id=snapshot_id, collection=collection)
    dataset = parse_files(raw, manifest)  # Validate everything before any publication.
    manifest['price_as_of'] = dataset.meta['as_of']
    output = Path(output)
    current = output / 'current.json'
    if current.exists():
        previous = json.loads(current.read_text())
        if previous.get('snapshot_id', previous['source_commit']) == snapshot_id and previous['files'] != records:
            raise PortfolioError('같은 원본 커밋의 내용이 달라졌습니다.', 'invalid_data')
        if all(previous['files'][name]['sha256'] == records[name]['sha256'] for name in FILES):
            from qsignals.portfolio_data import load_dataset
            load_dataset(output)
            return previous
    snapshot = output / 'snapshots' / snapshot_id
    snapshot.mkdir(parents=True, exist_ok=True)
    for name, data in raw.items():
        path = snapshot / name
        if path.exists() and path.read_bytes() != data:
            raise PortfolioError('기존 버전 파일 덮어쓰기를 거부했습니다.', 'invalid_data')
        path.write_bytes(data)
    if receipts:
        receipt_dir = snapshot / 'receipts'
        receipt_dir.mkdir(exist_ok=True)
        manifest['collection']['receipts'] = {}
        for name, content in receipts.items():
            if not re.fullmatch(r'[a-z0-9_-]+\.csv', name):
                raise PortfolioError('잘못된 수집 기록 경로입니다.', 'invalid_data')
            path = receipt_dir / name
            path.write_bytes(content)
            manifest['collection']['receipts'][name] = {
                'path': f'snapshots/{snapshot_id}/receipts/{name}',
                'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
    output.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output, prefix='.current-', suffix='.json')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, current)  # Readers see either complete old or complete new data.
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return manifest


def fetch_upstream(repo=DEFAULT_REPO, ref='main'):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise PortfolioError('owner/repository 형식이 필요합니다.')
    sha = ref if re.fullmatch(r'[a-f0-9]{40}', ref) else json.loads(
        _download(f'https://api.github.com/repos/{repo}/commits/{quote(ref, safe="")}'))['sha']
    if not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise PortfolioError('원본 커밋을 확인할 수 없습니다.')
    raw = {name: _download(f'https://raw.githubusercontent.com/{repo}/{sha}/data/portfolio/{name}')
           for name in FILES}
    return raw, sha


def import_remote(repo=DEFAULT_REPO, ref='main', output=DEFAULT_DATA):
    raw, sha = fetch_upstream(repo, ref)
    return publish(raw, repo, sha, output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-repo', default=DEFAULT_REPO)
    p.add_argument('--source-ref', default='main')
    p.add_argument('--output-dir', type=Path, default=DEFAULT_DATA)
    args = p.parse_args()
    manifest = import_remote(args.source_repo, args.source_ref, args.output_dir)
    print(f"Portfolio snapshot: {manifest['price_as_of']} · {manifest['source_commit']}")


if __name__ == '__main__':
    main()
