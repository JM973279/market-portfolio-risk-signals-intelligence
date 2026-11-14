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
   ECOS is downloaded only to bootstrap and then extended from run.py's verified
   rows. The snapshot copies end on the last date every channel has, so a late
   provider makes run.py report Korea as delayed instead of blocked.
3. Run run.py --collect inside the snapshot.
4. Write korea_scores.csv only if Korea is CURRENT for its expected session,
   and us_scores.csv when US history was reproduced (CURRENT or DELAYED).
   A market that does not qualify keeps its previous file. Scores older than
   (or relabeled against) the published CSV are never written. Exit 0 = all
   imported, 3 = partial (a market's data is late), 2 = nothing new (also when
   the providers do not answer), 1 = verification failure (BLOCKED, nothing
   written). The summary lists each market's lag; the workflow fails once one is
   more than qsignals.deferral.MAX_BEHIND sessions behind.

API keys are read from the V1 .env into the child environment only; they are
never printed or written (only a length + SHA-256 prefix fingerprint, so a
runner secret can be compared with a local .env). Before any download the KRX
key is checked with one request per KRX endpoint: a rejected key makes the V1
KRX downloaders retry every session since 2010 for hours, so they are skipped.
KRX feeds Korea only, so Korea is then reported as delayed from its cached
history while US is refreshed as usual; the summary's `key_rejected` makes the
workflow fail after publishing. `--check-keys` runs only the checks (KRX and ECOS). Run logs
and provider receipts stay in --work-root (outside this repo).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from qsignals.calendar import latest_closed_session, load_sessions
from qsignals.deferral import MAX_BEHIND, sessions_behind
from qsignals.import_scores import SOURCE_FILES, import_data, import_us

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
ECOS_CHANNELS = ("Korea_Treasury_3Y", "Korea_Corporate_AAminus_3Y")
DOWNLOADERS = ("download_krx_indices", "download_vkospi", "download_ecos_credit")
DOWNLOADER_FILES = {"download_krx_indices": "krx_indices.csv", "download_vkospi": "vkospi.csv",
                    "download_ecos_credit": "ecos_credit.csv"}
# A top-up of an existing cache takes minutes; an unreachable KRX makes the downloaders retry for hours.
TOP_UP_TIMEOUT = 45 * 60
NO_RESPONSE = "no response"
# Endpoints the V1 KRX downloaders call (same AUTH_KEY header). Service access is
# granted per endpoint in KRX Open API, so both are checked.
KRX_ENDPOINTS = {
    "download_krx_indices": "http://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd",
    "download_vkospi": "http://data-dbg.krx.co.kr/svc/apis/idx/drvprod_dd_trd",
}
KRX_CHECK_DATE = "20100104"  # first session the V1 downloaders request
# One ECOS row of the V1 credit series (817Y002 / Treasury 3Y).
ECOS_CHECK_URL = "https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/1/817Y002/D/20100104/20100108/010200000"


class ProvidersUnreachable(RuntimeError):
    """The key check got no response at all (network/provider outage, not a rejected key)."""


class RefreshError(RuntimeError):
    pass


class KeysRejected(SystemExit):
    """A provider refused a key; `names` lists the refused keys and `code` holds the report."""

    def __init__(self, message, names):
        super().__init__(message)
        self.names = names


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


def key_fingerprint(value):
    """Length and SHA-256 prefix, to compare a runner secret with a local .env without revealing it."""
    return f"len {len(value)}, sha256 {hashlib.sha256(value.encode()).hexdigest()[:8]}"


# KRX answers 401 with different messages (checked 2026-11-14): a value it does not know gets
# "Unauthorized Key"; a key it knows but may not call that service with gets "Unauthorized API Call".
KRX_SERVICE_HINT = ("KRX knows this key but refuses the service (Unauthorized API Call): replacing the secret "
                    "will not help. KRX supplies indices only (prices come from Yahoo): the V1 score's KOSPI200 "
                    "index (kospi_dd_trd) and the VKOSPI risk factor (drvprod_dd_trd). On openapi.krx.co.kr, "
                    "signed in as the account that issued this key, check both services' approval for it; apply "
                    "again if missing, or ask KRX if they show as approved, then re-run.")
UPDATE_HINT = "Update the value (repository secret on GitHub Actions, V1 .env locally) and run again."


def krx_rejection_hint(text):
    """The fix a provider's rejection message points to."""
    return KRX_SERVICE_HINT if "Unauthorized API Call" in text else UPDATE_HINT


def _http_get(url, headers=None, timeout=30):
    """(status, body); HTTP errors are returned, network errors raised."""
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _fetch(url, headers=None, attempts=3, wait=2.0):
    """_http_get with a short retry for network errors (never reports the URL: ECOS keys sit in its path)."""
    for attempt in range(1, attempts + 1):
        try:
            return _http_get(url, headers)
        except OSError as exc:  # URLError, timeouts, connection resets
            reason = getattr(exc, "reason", None) or type(exc).__name__
            if attempt == attempts:
                return None, f"unreachable after {attempts} attempts ({reason})".encode()
            time.sleep(wait * attempt)


def _json(body):
    try:
        return json.loads(body)
    except ValueError:
        return None


def check_krx_key(key):
    """One KRX request per downloader endpoint; returns problems ([] = accepted)."""
    problems = []
    for module, url in KRX_ENDPOINTS.items():
        status, body = _fetch(f"{url}?basDd={KRX_CHECK_DATE}", {"AUTH_KEY": key})
        data = _json(body)
        if status == 200 and isinstance(data, dict) and isinstance(data.get("OutBlock_1"), list):
            continue
        if isinstance(data, dict):
            message = data.get("respMsg") or "response without OutBlock_1"
        else:
            message = body[:120].decode(errors="replace").strip()
        problems.append(f"{url.rsplit('/', 1)[-1]} ({module}): {'HTTP ' + str(status) if status else NO_RESPONSE} {message}")
    return problems


def check_ecos_key(key):
    status, body = _fetch(ECOS_CHECK_URL.format(key=key))
    data = _json(body)
    if status == 200 and isinstance(data, dict) and "StatisticSearch" in data:
        return []
    if isinstance(data, dict) and "RESULT" in data:
        result = data["RESULT"]
        return [f"StatisticSearch: {result.get('CODE')} {result.get('MESSAGE')}"]
    return [f"StatisticSearch: {'HTTP ' + str(status) if status else NO_RESPONSE} {body[:120].decode(errors='replace').strip()}"]


def check_provider_keys(env, ecos):
    """Stop before collection when a provider rejects a key; print fingerprints either way."""
    checks = [("KRX_API_KEY", check_krx_key)] + ([("ECOS_API_KEY", check_ecos_key)] if ecos else [])
    failed = []
    for name, check in checks:
        problems = check(env[name])
        print(f"{name} ({key_fingerprint(env[name])}): {'rejected' if problems else 'accepted'}", file=sys.stderr)
        failed += [(name, problem) for problem in problems]
    if not failed:
        return
    lines = [f"- {name} {key_fingerprint(env[name])}: {problem}" for name, problem in failed]
    if all(f"): {NO_RESPONSE} " in problem or problem.startswith(f"StatisticSearch: {NO_RESPONSE}") for _, problem in failed):
        # Nothing answered: an outage, not a rejected key. The caller keeps the published data.
        raise ProvidersUnreachable("; ".join(problem for _, problem in failed))
    names = sorted({name for name, _ in failed})
    message = "\n".join([
        f"Provider rejected {', '.join(names)}.",
        *lines,
        *dict.fromkeys(krx_rejection_hint(problem) for _, problem in failed),
        "Compare fingerprints with `python3 -m qsignals.refresh --check-keys` on a machine where the keys work.",
    ])
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error title=API key rejected::{message.splitlines()[0]} {' '.join(lines)}", file=sys.stderr)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(f"### API key rejected\n\n{message}\n")
    raise KeysRejected(message, names)


def run_logged(cmd, cwd, env, log_path, timeout=None):
    # Unbuffered children: a cancelled or timed-out run keeps its full log.
    env = {**env, "PYTHONUNBUFFERED": "1"}
    with log_path.open("ab") as log:
        log.write(f"\n$ {' '.join(map(str, cmd))}\n".encode())
        log.flush()
        try:
            out = subprocess.run(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            log.write(f"\n(stopped after {timeout} s)\n".encode())
            return 124
    return out.returncode


def top_up_korea_raw(python, v1_tree, v1_data, env, log, download=True):
    # KRX must be topped up: run.py only fetches the last 14 days on top of
    # this history and refuses gaps over 90 days. ECOS is fetched in full by
    # run.py itself, and calling it twice within seconds gets the second
    # request rejected, so the ECOS downloader only runs to bootstrap.
    modules = list(DOWNLOADERS)
    if (v1_data / "raw" / "korea" / "ecos_credit.csv").exists():
        modules.remove("download_ecos_credit")
    raw = v1_data / "raw" / "korea"
    if not download:
        # KRX refused the key: its downloaders would retry every session for hours. run.py's own
        # KRX request fails at once (HTTP 401 is not retried), so Korea falls back to this cached
        # history and is reported as delayed while US is refreshed as usual.
        modules = []
    for module in modules:
        cached = (raw / DOWNLOADER_FILES[module]).exists()
        code = run_logged([python, "-m", f"src.korea.{module}", "--data-root", str(v1_data)], v1_tree, env, log,
                          timeout=TOP_UP_TIMEOUT if cached else None)
        if code != 0 and not cached:
            raise RefreshError(f"V1 downloader {module} failed (exit {code}); see {log}")
        if code != 0:
            # run.py refetches KRX itself from 14 days before the cached history, so a failed
            # top-up only means the cache advances on a later run.
            print(f"::warning::V1 downloader {module} failed (exit {code}); continuing with the cached history.",
                  file=sys.stderr)
    target = v1_tree / "data" / "raw" / "korea"
    target.mkdir(parents=True, exist_ok=True)
    for name in KOREA_RAW:
        if not (raw / name).exists():
            raise RefreshError(f"Korea raw history missing after download: {raw / name}")
        shutil.copy2(raw / name, target / name)
    common = align_korea_fallback(target)
    with log.open("a", encoding="utf-8") as out:
        out.write(f"\nKorea fallback history in the snapshot aligned to {common}\n")


def _csv_last_date(path, keep=lambda row: True):
    with path.open(encoding="utf-8-sig", newline="") as f:
        dates = [row["Date"] for row in csv.DictReader(f) if keep(row)]
    if not dates:
        raise RefreshError(f"Korea raw history has no rows: {path}")
    return max(dates)


def _trim_csv(path, last):
    """Drop rows after `last` (ISO date in the first column), keeping every other byte."""
    lines = path.read_bytes().splitlines(keepends=True)
    kept = lines[:1] + [line for line in lines[1:] if line.split(b",", 1)[0].strip() <= last.encode()]
    if len(kept) != len(lines):
        path.write_bytes(b"".join(kept))


def align_korea_fallback(korea_dir):
    """Trim the snapshot's Korea history to the last date every channel has.

    run.py falls back to this history when a provider fetch fails (KRX has not posted the
    due session yet). KRX is topped up every run but ECOS only through run.py, so the
    copies can end on different dates, and run.py then blocks the market ('Missing Korea
    equity-date channel; no imputation') instead of reporting it as delayed. Only the
    snapshot copies are trimmed; the cache keeps everything (run.py refetches KRX from 14
    days before this date). Returns the common date.
    """
    korea_dir = Path(korea_dir)
    common = min(
        _csv_last_date(korea_dir / "krx_indices.csv", lambda r: r["Index"] == "KOSPI200"),
        _csv_last_date(korea_dir / "vkospi.csv", lambda r: (r.get("Close") or "").strip() != ""),
        _csv_last_date(korea_dir / "ecos_credit.csv",
                       lambda r: all((r.get(c) or "").strip() for c in ECOS_CHANNELS)))
    for name in KOREA_RAW:
        _trim_csv(korea_dir / name, common)
    return common


def extend_ecos_cache(collected, cache):
    """Append the run's verified ECOS rows past the cache's last date.

    `collected` is run.py's korea/ecos_credit.csv (provider data on KOSPI200 sessions, every
    channel present). It is used only when it agrees exactly with every cached row, so a
    provider revision never rewrites history silently. Returns the number of rows added.
    """
    collected, cache = Path(collected), Path(cache)
    if not collected.exists() or not cache.exists():
        return 0

    def rows(path):
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            return next(reader), [row for row in reader if row]

    head_new, new = rows(collected)
    head_old, old = rows(cache)
    if head_new != head_old:
        return 0
    by_date = {row[0]: row for row in new}
    if any(by_date.get(row[0]) != row for row in old):
        return 0
    last = max(row[0] for row in old) if old else ""
    added = [row for row in new if row[0] > last]
    if not added:
        return 0
    body = cache.read_bytes()
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(added)
    cache.write_bytes(body + (b"" if body.endswith(b"\n") else b"\n") + stream.getvalue().encode())
    return len(added)


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


def expected_session(market, now):
    """The session run.py expects at `now`: Korea close + 6 h; US close (21:00 UTC) + 12 h.

    US holidays are not in this calendar, so they count as sessions: in a holiday week the
    US lag alert can come a day early, never late.
    """
    if market == "korea":
        return latest_closed_session(now, publication_lag_hours=6)
    day = (now.astimezone(timezone.utc) - timedelta(hours=33)).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def score_lag(output_dir, now):
    """{market: {published, expected, behind}} for the published data/input score files."""
    lag = {}
    for market in ("korea", "us"):
        path = Path(output_dir) / f"{market}_scores.csv"
        rows = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        published = rows[-1].split(",", 1)[0] if len(rows) > 1 else None
        expected = expected_session(market, now)
        if market == "korea":
            days = [d for d in load_sessions() if d <= expected]
        else:
            first = date.fromisoformat(published or expected) - timedelta(days=1)
            days = [(first + timedelta(days=i)).isoformat() for i in range((date.fromisoformat(expected) - first).days + 1)]
            days = [d for d in days if date.fromisoformat(d).weekday() < 5]
        lag[market] = {"published": published, "expected": expected,
                       "behind": sessions_behind(days, published) if published else None}
    return lag


def with_lag(summary, output_dir, now=None):
    """Adds lag and the markets too far behind ('stale'): the workflow fails on those after publishing."""
    lag = score_lag(output_dir, now or datetime.now(timezone.utc))
    summary["lag"] = lag
    summary["stale"] = [m for m, v in lag.items() if v["behind"] is None or v["behind"] > MAX_BEHIND]
    return summary


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
    parser.add_argument("--check-keys", action="store_true",
                        help="only check KRX_API_KEY and ECOS_API_KEY with the providers and print fingerprints")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    env.update(load_env(args.env_file or args.v1_repo / ".env"))
    for key in ("KRX_API_KEY", "ECOS_API_KEY"):
        if not env.get(key):
            raise SystemExit(f"{key} is not set (V1 .env or environment)")
    # KRX only on a refresh: its downloaders retry each session for hours on a
    # rejected key, while ECOS fails within seconds by itself, and an extra ECOS
    # call shortly before the real fetch can get that fetch rejected.
    key_alert = None
    try:
        check_provider_keys(env, ecos=args.check_keys)
    except KeysRejected as exc:
        if args.check_keys or exc.names != ["KRX_API_KEY"]:
            raise SystemExit(f"{exc.code}\nNothing was collected or published.") from None
        # KRX feeds Korea only. US needs no KRX data, so a refused KRX key must not stop US.
        key_alert = " ".join(exc.code.splitlines())
        print("::warning::KRX refused the key: Korea keeps its published scores; US is refreshed as usual "
              "and the run fails after publishing.", file=sys.stderr)
    except ProvidersUnreachable as exc:
        if args.check_keys:
            raise SystemExit(f"Providers unreachable: {exc}") from None
        print(json.dumps(with_lag({"unreachable": str(exc)}, args.output_dir), indent=2, ensure_ascii=False))
        print(f"::warning::Providers unreachable ({exc}); kept the published files.", file=sys.stderr)
        return 2
    if args.check_keys:
        return 0

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

    env["PYTHONPATH"] = str(work / "v1")

    args.v1_data.mkdir(parents=True, exist_ok=True)
    top_up_korea_raw(args.python, work / "v1", args.v1_data, env, log, download=key_alert is None)

    original_reference = (work / "mpri" / contract["markets"]["korea"]["reference"]).exists()
    if not original_reference and (args.rebuild_reference or not (args.reference_dir / "verification.json").exists()):
        rebuild_reference(args.python, work, args.v1_data, args.reference_dir, args.reference_end, log)
    reference = install_reference(work, contract, args.reference_dir)

    env.pop("PYTHONPATH")
    code = run_logged([args.python, RUNNER, "--collect", "--original-v1-root", str(work / "v1")], work / "mpri", env, log)
    if code != 0:
        raise SystemExit(f"Frozen pipeline failed (exit {code}); see {log}")
    operational = json.loads((work / "mpri/frontend/public/data/operational-markets.json").read_text(encoding="utf-8"))
    # The ECOS downloader runs only to bootstrap, so the cache follows run.py's verified rows.
    added = extend_ecos_cache(work / "mpri/data/operations" / str(operational.get("runId")) / "korea/ecos_credit.csv",
                              args.v1_data / "raw/korea/ecos_credit.csv")
    if added:
        print(f"ECOS credit cache extended by {added} verified rows.", file=sys.stderr)
    status = {m: freshness(v) for m, v in operational["markets"].items()}
    summary = {"run_id": operational.get("runId"), "work_dir": str(work), "korea_reference": reference or {"rebuilt": False}, "markets": status}
    if key_alert:
        summary["key_rejected"] = key_alert  # the workflow fails on this after publishing

    try:
        remote = git(args.source_root, "remote", "get-url", "origin")
        source_repo = remote.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    except RefreshError:
        source_repo = args.source_root.resolve().name
    try:
        branch = git(args.source_root, "rev-parse", "--abbrev-ref", args.source_ref)
    except RefreshError:
        branch = None
    # Exit codes (the daily workflow publishes on 0 and 3 only):
    #   0  every market imported or already up to date
    #   3  partial: a market's data is late (Korea not CURRENT / US DELAYED without
    #      new verified rows) but the other market was imported -> publish it
    #   2  nothing new: every market late, nothing written
    #   1  verification failure (BLOCKED: historical reproduction failed) -> nothing
    #      written, nothing published. Pipeline errors exit non-zero via SystemExit.
    blocked = sorted(m for m, v in operational["markets"].items() if v.get("status") == "BLOCKED")
    if blocked:
        summary["blocked"] = blocked
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"Verification failed (BLOCKED: {', '.join(blocked)}); data/input/ left unchanged.", file=sys.stderr)
        return 1
    # Korea is written only when CURRENT; US whenever its history was verified.
    markets = tuple(m for m, ok in (("korea", status["korea"]["fresh"]),
                                    ("us", us_importable(operational["markets"]["us"]))) if ok)
    summary["delayed"] = [m for m in ("korea", "us") if m not in markets]
    if not markets:
        print(json.dumps(with_lag(summary, args.output_dir), indent=2, ensure_ascii=False))
        print("No market has new verified data yet; data/input/ left unchanged.", file=sys.stderr)
        return 2
    # Same import as qsignals.import_scores (calendar coverage, KOSPI200 price
    # check), fed with this run's exports instead of the committed ones.
    raw = {key: (work / "mpri" / rel).read_bytes() for key, rel in SOURCE_FILES.items()}
    payloads = {key: json.loads(data) for key, data in raw.items()}
    files = {key: {"path": SOURCE_FILES[key], "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
             for key, data in raw.items()}
    source = {
        "source_repo": source_repo,
        "source_repo_url": None,
        "source_git_branch": branch if branch and branch != "HEAD" else None,
        "source_git_ref": args.source_ref,
        "source_git_commit": source_commit,
        "source_files_modified_locally": False,
    }
    refresh = {
        "mode": operational.get("mode"),
        "v1_commit": v1_commit,
        "generated_at": operational.get("generatedAt"),
        "korea_reference": reference or {"rebuilt": False},
        "korea": {**status["korea"], "imported": "korea" in markets},
        "us": {**status["us"], "imported": "us" in markets,
               "provider_revision": operational["markets"]["us"].get("providerRevision")},
    }
    summary["imported"], summary["skipped"], summary["last_risk_date"] = [], {}, {}
    for market in markets:
        importer = import_data if market == "korea" else import_us
        result = importer(payloads, files, source, args.output_dir, extra={"refresh": refresh})
        summary["last_risk_date"][market] = result.get("last_risk_date")
        if result.get("publication", {}).get("status") == "skipped":
            # Older or relabeled scores never replace what is already published.
            summary["skipped"][market] = result["publication"]
        else:
            summary["imported"].append(market)
    print(json.dumps(with_lag(summary, args.output_dir), indent=2, ensure_ascii=False))
    if summary["delayed"]:
        print(f"Late data for {', '.join(summary['delayed'])}; kept the published files for it.", file=sys.stderr)
        return 3
    return 0

if __name__ == "__main__":
    sys.exit(main())
