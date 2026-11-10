"""Collect the latest Korea and US V1 scores without touching the deployed repo.

    python3 -m qsignals.refresh [--python PATH] [--v1-repo PATH] [--source-root PATH]

The deployed project's frozen pipeline (market_engine/operations/run.py) is
the only code that may produce V1 scores. This command runs it unchanged, in
throwaway snapshots, and then imports the Korea and US series:

1. Snapshot the deployed repo (git archive of --source-ref) and the original V1
   repo at the commit whose sources match the pipeline's contract.json. The
   V1 working tree may be on any branch; it is never checked out or modified.
2. Top up the Korea raw history (KRX KOSPI200, VKOSPI, ECOS credit) with the V1
   downloaders into --v1-data. These files are gitignored in V1, so the first
   run downloads the full history from 2010; later runs fetch only new days.
3. Run run.py --collect inside the snapshot.
4. Write korea_scores.csv only if Korea is CURRENT for its expected session,
   and us_scores.csv when US history was reproduced (CURRENT or DELAYED).
   A market that does not qualify keeps its previous file; a stale Korea run
   exits 2 even when US was updated.

API keys are read from the V1 .env into the child environment only; they are
never printed or written. Run logs and provider receipts stay in --work-root
(outside this repo).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from qsignals.import_scores import import_scores

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
DEFAULT_SOURCE = PROJECT_ROOT.parent / "market-portfolio-risk-intelligence"
DEFAULT_V1 = PROJECT_ROOT.parent
DEFAULT_PYTHON = Path(os.environ.get("QSIGNALS_INFERENCE_PYTHON", HOME / ".venvs/mpri-inference/bin/python"))
DEFAULT_V1_DATA = HOME / ".cache/qsignals/v1-data"
DEFAULT_WORK_ROOT = HOME / ".cache/qsignals/runs"
DEFAULT_REFERENCE_DIR = HOME / ".cache/qsignals/reference"
# Official Korea MSI/targets behind the original reference ended here
# (3,724 rows; 3,714 labeled Target_10D rows, matching the training evidence).
REFERENCE_END = "2026-10-02"
CONTRACT = "market_engine/operations/contract.json"
RUNNER = "market_engine/operations/run.py"
KOREA_RAW = ("krx_indices.csv", "vkospi.csv", "ecos_credit.csv")
DOWNLOADERS = ("download_krx_indices", "download_vkospi", "download_ecos_credit")


class RefreshError(RuntimeError):
    pass


def git(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if out.returncode != 0:
        raise RefreshError(f"git {' '.join(args[:2])} failed: {out.stderr.decode(errors='replace').strip()}")
    return out.stdout if binary else out.stdout.decode().strip()


def archive(repo, ref, dest):
    """Extract `ref` of `repo` into `dest` without touching its worktree."""
    data = git(repo, "archive", "--format=tar", ref, binary=True)
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:  # Python < 3.12; git archive output has no absolute or .. paths
            tar.extractall(dest)
    return git(repo, "rev-parse", ref)


def find_v1_commit(v1_repo, sources):
    """Newest commit (any ref) whose files match every contract SHA-256."""
    revs = git(v1_repo, "rev-list", "--all", "--", *sources).split()
    best = (0, None)
    for rev in revs:
        matched = 0
        for rel, sha in sources.items():
            out = subprocess.run(["git", "-C", str(v1_repo), "show", f"{rev}:{rel}"], capture_output=True)
            if out.returncode == 0 and hashlib.sha256(out.stdout).hexdigest() == sha:
                matched += 1
        if matched == len(sources):
            return rev
        best = max(best, (matched, rev), key=lambda item: item[0])
    raise RefreshError(
        f"No V1 commit matches the pipeline contract ({best[0]}/{len(sources)} files at best, {best[1]}). "
        "The frozen pipeline cannot run against a different V1 version."
    )


def load_env(path):
    """KEY=VALUE pairs from a dotenv file; values are never logged."""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        env[key] = value
    return env


def run_logged(cmd, cwd, env, log_path):
    with log_path.open("ab") as log:
        log.write(f"\n$ {' '.join(map(str, cmd))}\n".encode())
        log.flush()
        out = subprocess.run(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    return out.returncode


def top_up_korea_raw(python, v1_tree, v1_data, env, log):
    # KRX must be topped up: run.py only fetches the last 14 days on top of
    # this history and refuses gaps over 90 days. ECOS is fetched in full by
    # run.py itself, and calling it twice within seconds gets the second
    # request rejected, so the ECOS downloader only runs to bootstrap.
    modules = list(DOWNLOADERS)
    if (v1_data / "raw" / "korea" / "ecos_credit.csv").exists():
        modules.remove("download_ecos_credit")
    for module in modules:
        code = run_logged([python, "-m", f"src.korea.{module}", "--data-root", str(v1_data)], v1_tree, env, log)
        if code != 0:
            raise RefreshError(f"V1 downloader {module} failed (exit {code}); see {log}")
    raw = v1_data / "raw" / "korea"
    target = v1_tree / "data" / "raw" / "korea"
    target.mkdir(parents=True, exist_ok=True)
    for name in KOREA_RAW:
        if not (raw / name).exists():
            raise RefreshError(f"Korea raw history missing after download: {raw / name}")
        shutil.copy2(raw / name, target / name)


def prune_runs(work_root, keep):
    """Delete older snapshot folders (names are UTC stamps, so they sort by time)."""
    runs = sorted(p for p in Path(work_root).iterdir() if p.is_dir() and p.name[:8].isdigit())
    for old in runs[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rebuild_reference(python, work, v1_data, reference_dir, end, log):
    """Run qsignals/_reference_worker.py (pandas/joblib) under the inference Python."""
    reference_dir.mkdir(parents=True, exist_ok=True)
    worker = Path(__file__).with_name("_reference_worker.py")
    code = run_logged([python, str(worker), "--v1-tree", str(work / "v1"), "--mpri-tree", str(work / "mpri"),
                       "--raw-dir", str(v1_data / "raw" / "korea"), "--end", end, "--out-dir", str(reference_dir)],
                      work, dict(os.environ), log)
    if code != 0:
        raise RefreshError(f"Rebuilt Korea reference failed verification (exit {code}); see {log}")


def install_reference(work, contract, reference_dir):
    """Use a verified rebuild only when the snapshot lacks the original reference.

    The rebuilt file has a different SHA-256 from the original, so the
    snapshot's contract.json (never the deployed repo's) is pointed at the
    rebuilt hash. Returns provenance, or None when the original is present.
    """
    korea = contract["markets"]["korea"]
    target = work / "mpri" / korea["reference"]
    if target.exists():
        return None
    verification_path = reference_dir / "verification.json"
    if not verification_path.exists():
        raise RefreshError(f"Korea reference missing and no verified rebuild in {reference_dir}")
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    rebuilt = reference_dir / Path(korea["reference"]).name
    if not verification.get("passed"):
        raise RefreshError("Rebuilt Korea reference did not pass verification")
    if verification.get("contract_reference_sha256") != korea["reference_sha256"]:
        raise RefreshError("Rebuilt Korea reference belongs to a different contract; rebuild it")
    if not rebuilt.exists() or sha256_file(rebuilt) != verification.get("rebuilt_sha256"):
        raise RefreshError("Rebuilt Korea reference changed after verification; rebuild it")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rebuilt, target)
    korea["reference_sha256"] = verification["rebuilt_sha256"]
    (work / "mpri" / CONTRACT).write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "rebuilt": True,
        "original_sha256": verification["contract_reference_sha256"],
        "rebuilt_sha256": verification["rebuilt_sha256"],
        "end": verification.get("end"),
        "checks": verification.get("checks"),
    }


def freshness(market):
    """CURRENT only when the frozen pipeline verified its expected session."""
    current = market.get("current") or {}
    ok = market.get("status") == "CURRENT" and current.get("date") == market.get("expectedDate")
    return {
        "status": market.get("status"),
        "expected_date": market.get("expectedDate"),
        "current_date": current.get("date"),
        "last_valid_date": (market.get("lastValid") or {}).get("date"),
        "fresh": ok,
        "reason": market.get("reason"),
        "series": {s["name"]: s.get("observationDate") for s in market.get("series", [])},
    }


def us_importable(market):
    """US rows are written when the pipeline reproduced history and scored dates.

    DELAYED is fine (FRED credit data often lag SPY/VIX by a few sessions): the
    rows stop at the last fully observed date. BLOCKED/UNAVAILABLE keep the
    previous us_scores.csv.
    """
    return (market.get("status") in ("CURRENT", "DELAYED") and market.get("historicalParity") is True
            and bool(market.get("history")))


def save_status_blocks(operational, output_dir):
    """Keep each market's latest verified pipeline block in data/input/operational/.

    These are the public (price-free) per-market blocks of the pipeline's
    export: status, expected date, source observation dates, history. The
    frontend export reads them for the status panels; the score CSVs stay the
    source of the numbers (qsignals.export_frontend checks they agree). A
    market whose history did not reproduce keeps its previous block.
    """
    saved = []
    for market, block in operational["markets"].items():
        if block.get("historicalParity") is not True:
            continue
        path = Path(output_dir) / "operational" / f"{market}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {k: operational.get(k) for k in ("schema_version", "runId", "generatedAt", "mode", "sourceValuesIncluded")}
        path.write_text(json.dumps({**meta, "market": market, "block": block}, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        saved.append(market)
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON, help="interpreter with market_engine/operations/requirements.txt")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE, help="deployed repo (read via git archive)")
    parser.add_argument("--source-ref", default="HEAD")
    parser.add_argument("--v1-repo", type=Path, default=DEFAULT_V1, help="original V1 repo (read via git archive)")
    parser.add_argument("--env-file", type=Path, help="defaults to <v1-repo>/.env")
    parser.add_argument("--v1-data", type=Path, default=DEFAULT_V1_DATA, help="persistent Korea raw history cache")
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument("--keep-runs", type=int, default=3, help="snapshot folders kept in --work-root (~110 MB each)")
    parser.add_argument("--reference-dir", type=Path, default=DEFAULT_REFERENCE_DIR,
                        help="verified rebuild of the gitignored Korea reference matrix")
    parser.add_argument("--reference-end", default=REFERENCE_END,
                        help="raw end date the original reference was built with")
    parser.add_argument("--rebuild-reference", action="store_true", help="rebuild and re-verify it even if present")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data" / "input")
    args = parser.parse_args(argv)

    if not args.python.exists():
        raise SystemExit(f"Inference Python not found: {args.python} (see scripts/setup_inference_env.sh)")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = args.work_root / stamp
    work.mkdir(parents=True)
    prune_runs(args.work_root, max(args.keep_runs, 1))
    log = work / "refresh.log"

    source_commit = archive(args.source_root, args.source_ref, work / "mpri")
    contract = json.loads((work / "mpri" / CONTRACT).read_text(encoding="utf-8"))
    v1_commit = find_v1_commit(args.v1_repo, contract["original_sources"])
    archive(args.v1_repo, v1_commit, work / "v1")

    env = dict(os.environ)
    env.update(load_env(args.env_file or args.v1_repo / ".env"))
    env["PYTHONPATH"] = str(work / "v1")
    for key in ("KRX_API_KEY", "ECOS_API_KEY"):
        if not env.get(key):
            raise SystemExit(f"{key} is not set (V1 .env or environment)")

    args.v1_data.mkdir(parents=True, exist_ok=True)
    top_up_korea_raw(args.python, work / "v1", args.v1_data, env, log)

    original_reference = (work / "mpri" / contract["markets"]["korea"]["reference"]).exists()
    if not original_reference and (args.rebuild_reference or not (args.reference_dir / "verification.json").exists()):
        rebuild_reference(args.python, work, args.v1_data, args.reference_dir, args.reference_end, log)
    reference = install_reference(work, contract, args.reference_dir)

    env.pop("PYTHONPATH")
    code = run_logged([args.python, RUNNER, "--collect", "--original-v1-root", str(work / "v1")], work / "mpri", env, log)
    if code != 0:
        raise SystemExit(f"Frozen pipeline failed (exit {code}); see {log}")
    operational = json.loads((work / "mpri/frontend/public/data/operational-markets.json").read_text(encoding="utf-8"))
    status = {m: freshness(v) for m, v in operational["markets"].items()}
    summary = {"run_id": operational.get("runId"), "work_dir": str(work), "korea_reference": reference or {"rebuilt": False}, "markets": status}
    summary["status_blocks_saved"] = save_status_blocks(operational, args.output_dir)

    try:
        remote = git(args.source_root, "remote", "get-url", "origin")
        source_repo = remote.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    except RefreshError:
        source_repo = args.source_root.resolve().name
    try:
        branch = git(args.source_root, "rev-parse", "--abbrev-ref", args.source_ref)
    except RefreshError:
        branch = None
    # Korea is written only when CURRENT; US whenever its history was verified.
    # A stale Korea run still updates US but exits 2 so schedulers notice.
    markets = tuple(m for m, ok in (("korea", status["korea"]["fresh"]),
                                    ("us", us_importable(operational["markets"]["us"]))) if ok)
    if not markets:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print("Neither market is importable; data/input/ left unchanged.", file=sys.stderr)
        return 2
    provenance = import_scores(work / "mpri", args.output_dir, {
        "source_repo": source_repo,
        "source_git_branch": branch if branch and branch != "HEAD" else None,
        "source_git_ref": args.source_ref,
        "source_git_commit": source_commit,
        "source_files_modified_locally": False,
        "refresh": {
            "mode": operational.get("mode"),
            "v1_commit": v1_commit,
            "generated_at": operational.get("generatedAt"),
            "korea_reference": reference or {"rebuilt": False},
            "korea": {**status["korea"], "imported": "korea" in markets},
            "us": {**status["us"], "imported": "us" in markets,
                   "provider_revision": operational["markets"]["us"].get("providerRevision")},
        },
    }, markets)
    summary["imported"] = list(markets)
    summary["last_risk_date"] = {m: v["last_risk_date"] for m, v in provenance["markets"].items()}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if "korea" not in markets:
        print("Korea is not CURRENT; korea_scores.csv left unchanged (US updated).", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
