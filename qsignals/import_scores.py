"""Import pinned V1 exports and separately verified event-return prices."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from qsignals.calendar import latest_closed_session, load_sessions, require_coverage
from qsignals.prices import fetch_prices, parse_prices
from qsignals.scores import build_rows, write_scores

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO = "tina77302/market-portfolio-risk-intelligence"
SOURCE_FILES = {
    "global_markets": "frontend/public/data/global-markets.json",
    "operational_markets": "frontend/public/data/operational-markets.json",
}


def _git(source_root, *args):
    try:
        out = subprocess.run(["git", "-C", str(source_root), *args], capture_output=True,
                             text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def _download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "market-qualitative-signals"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError("Source export exceeds size limit")
    return raw


def load_source(source_root=None, source_repo=DEFAULT_REPO, source_ref="main"):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source_repo):
        raise ValueError("Expected owner/repository")
    if source_root is not None:
        root = Path(source_root).resolve()
        if not (root / ".git").exists():
            raise ValueError("Local source must be a Git checkout")
        remote = _git(root, "remote", "get-url", "origin")
        metadata = {
            "source_repo": remote.removeprefix("https://github.com/").removesuffix(".git") if remote and remote.startswith("https://github.com/") else root.name,
            "source_repo_url": remote,
            "source_git_branch": _git(root, "branch", "--show-current"),
            "source_git_commit": _git(root, "rev-parse", "HEAD"),
            "source_files_modified_locally": bool(_git(root, "status", "--porcelain", "--", *SOURCE_FILES.values())),
        }
        raw_files = {key: (root / rel).read_bytes() for key, rel in SOURCE_FILES.items()}
        if any((root / SOURCE_FILES[key]).read_bytes() != raw for key, raw in raw_files.items()):
            raise ValueError("Source changed during import")
    else:
        if re.fullmatch(r"[0-9a-f]{40}", source_ref):
            sha = source_ref
        else:
            ref = urllib.parse.quote(source_ref, safe="")
            sha = json.loads(_download(f"https://api.github.com/repos/{source_repo}/commits/{ref}"))["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("Invalid source commit")
        metadata = {
            "source_repo": source_repo, "source_repo_url": f"https://github.com/{source_repo}",
            "source_git_branch": source_ref, "source_git_commit": sha,
            "source_files_modified_locally": False,
        }
        raw_files = {key: _download(f"https://raw.githubusercontent.com/{source_repo}/{sha}/{rel}")
                     for key, rel in SOURCE_FILES.items()}
    return {key: json.loads(raw) for key, raw in raw_files.items()}, {
        key: {"path": SOURCE_FILES[key], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for key, raw in raw_files.items()
    }, metadata


def import_data(payloads, files, source, output_dir, *, price_replay=None):
    output_dir = Path(output_dir)
    original = build_rows(payloads["global_markets"], payloads["operational_markets"])
    if not original or not any(r.risk_v1 is not None for r in original):
        raise ValueError("Empty or unscored source export")
    through = max(original[-1].date, latest_closed_session(publication_lag_hours=1))
    require_coverage(original[0].date, through)
    if price_replay:
        replay = json.loads(Path(price_replay).read_text())
        price_meta = replay["price_source"]
        through = max(original[-1].date, price_meta["last_date"])
        raw = (Path(price_replay).parent / "kospi200_naver.xml").read_bytes()
        if hashlib.sha256(raw).hexdigest() != price_meta["sha256"]:
            raise ValueError("Price replay hash mismatch")
        prices = parse_prices(raw, through)
    else:
        prices, raw, price_meta = fetch_prices(through)
    overlap = [r for r in original if r.date in prices and r.kospi200_close is not None]
    if len(overlap) < 5:
        raise ValueError("Insufficient price-provider overlap with frozen reference")
    rows = build_rows(payloads["global_markets"], payloads["operational_markets"], prices)
    sessions = load_sessions()
    actual = {r.date for r in rows}
    if actual - set(sessions):
        raise ValueError("Source observations include a non-KRX session")
    expected = {d for d in sessions if rows[0].date <= d <= rows[-1].date}
    missing = sorted(expected - actual)
    ops = payloads["operational_markets"]["markets"]["korea"]
    scored = [r for r in rows if r.risk_v1 is not None]
    priced = [r for r in rows if r.kospi200_close is not None]
    price_meta = {**price_meta, "frozen_overlap_rows": len(overlap),
                  "frozen_max_abs_difference": max(abs(r.kospi200_close - prices[r.date]) for r in overlap)}
    provenance = {
        "schema_version": 2, **source,
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": files, "operational_run_id": payloads["operational_markets"].get("runId"),
        "operational_model_sha256": ops.get("modelSha256"), "training_cutoff": ops.get("trainingCutoff"),
        "korea_generated_at": ops.get("generatedAt", payloads["operational_markets"].get("generatedAt")),
        "korea_expected_date": ops.get("expectedDate"), "korea_source_status": ops.get("status"),
        "rows": len(rows), "record_type_counts": dict(sorted(Counter(r.record_type for r in rows).items())),
        "first_date": rows[0].date, "last_date": rows[-1].date,
        "last_risk_date": scored[-1].date, "last_price_date": priced[-1].date,
        "missing_sessions": missing, "price_source": price_meta,
        "calendar_sha256": hashlib.sha256((PROJECT_ROOT / "data/calendar/xkrx_sessions.csv").read_bytes()).hexdigest(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_dir) as temp:
        stage = Path(temp)
        write_scores(rows, stage / "korea_scores.csv")
        provenance["scores_sha256"] = hashlib.sha256((stage / "korea_scores.csv").read_bytes()).hexdigest()
        old_path = output_dir / "provenance.json"
        if old_path.exists():
            old = json.loads(old_path.read_text())
            ignored = {"imported_at", "price_source"}
            same_meta = {k:v for k,v in old.items() if k not in ignored} == {k:v for k,v in provenance.items() if k not in ignored}
            same_price = {k:v for k,v in old.get("price_source", {}).items() if k != "retrieved_at"} == {k:v for k,v in price_meta.items() if k != "retrieved_at"}
            same_files = all((output_dir / name).exists() and hashlib.sha256((output_dir / name).read_bytes()).hexdigest() == sha
                             for name, sha in [("korea_scores.csv", provenance["scores_sha256"]), ("kospi200_naver.xml", price_meta["sha256"])])
            if same_meta and same_price and same_files:
                return old
        (stage / "kospi200_naver.xml").write_bytes(raw)
        (stage / "provenance.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for name in ("kospi200_naver.xml", "korea_scores.csv", "provenance.json"):
            os.replace(stage / name, output_dir / name)
    return provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--source-repo", default=DEFAULT_REPO)
    parser.add_argument("--source-ref", default="main")
    parser.add_argument("--price-replay", type=Path, help="Replay retained provenance + raw prices without provider access")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data/input")
    args = parser.parse_args(argv)
    payloads, files, source = load_source(args.source_root, args.source_repo, args.source_ref)
    provenance = import_data(payloads, files, source, args.output_dir, price_replay=args.price_replay)
    print(json.dumps({k: provenance[k] for k in ("source_git_commit", "last_risk_date", "last_price_date", "rows", "korea_source_status", "missing_sessions")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
