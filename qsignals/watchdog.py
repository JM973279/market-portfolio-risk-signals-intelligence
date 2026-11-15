"""Start a data workflow whose scheduled run GitHub dropped or is holding back.

    python3 -m qsignals.watchdog            # in GitHub Actions (GH_TOKEN, GITHUB_REPOSITORY)
    python3 -m qsignals.watchdog --dry-run  # only report what it would start

GitHub runs `schedule` events best effort: on this repository scheduled runs started 0.1-17.6 h
late and some never started (measured 2026-11-11..14). For each watched workflow this reads the
cron lines of its own file, takes the latest slot that is more than GRACE old, and starts the
workflow with workflow_dispatch (which starts at once) when no run of it was created since that
slot. Every watched workflow is idempotent and publishes only verified data, so a late scheduled
run arriving afterwards is harmless. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github/workflows"
WATCHED = (
    "daily-refresh.yml",
    "refresh-korea-portfolio.yml",
    "refresh-diagnostics.yml",
    "refresh-overnight.yml",
    "refresh-portfolio.yml",
    "update-krx-calendar.yml",
)
GRACE = timedelta(minutes=45)
LOOKBACK = timedelta(days=16)  # covers the twice-monthly calendar schedule
CRON = re.compile(r"""^\s*-\s*cron:\s*['"]([^'"]+)['"]""", re.M)


def crons(workflow):
    return CRON.findall((WORKFLOWS / workflow).read_text(encoding="utf-8"))


def _field(spec, low, high):
    """Values of one cron field: '*', '*/n', 'a', 'a-b', 'a-b/n' and comma lists."""
    values = set()
    for part in spec.split(","):
        base, _, step = part.partition("/")
        if base == "*":
            start, end = low, high
        elif "-" in base:
            start, end = (int(x) for x in base.split("-"))
        else:
            start = end = int(base)
        values.update(range(start, end + 1, int(step) if step else 1))
    return values


def parse(cron):
    minute, hour, dom, month, dow = cron.split()
    return (_field(minute, 0, 59), _field(hour, 0, 23), _field(dom, 1, 31), _field(month, 1, 12),
            {d % 7 for d in _field(dow, 0, 7)}, dom != "*" and dow != "*")


def _hit(fields, moment):
    minutes, hours, doms, months, dows, either = fields
    if moment.minute not in minutes or moment.hour not in hours or moment.month not in months:
        return False
    dom_ok, dow_ok = moment.day in doms, (moment.weekday() + 1) % 7 in dows  # cron: 0 = Sunday
    # Cron semantics: when both day fields are restricted, either one may match.
    return (dom_ok or dow_ok) if either else (dom_ok and dow_ok)


def matches(cron, moment):
    return _hit(parse(cron), moment)


def latest_slot(cron_lines, now, grace=GRACE):
    """The latest scheduled time (UTC) at or before now - grace, within LOOKBACK."""
    parsed = [parse(c) for c in cron_lines]
    moment = (now - grace).replace(second=0, microsecond=0)
    stop = moment - LOOKBACK
    while moment > stop:
        if any(_hit(f, moment) for f in parsed):
            return moment
        moment -= timedelta(minutes=1)
    return None


def api(method, path, token, body=None):
    request = urllib.request.Request(
        f"https://api.github.com{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "mpri-schedule-watchdog"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
    return json.loads(data) if data else {}


def runs_since(repo, workflow, since, token):
    created = urllib.parse.quote(">=" + since.strftime("%Y-%m-%dT%H:%M:%SZ"), safe="")
    result = api("GET", f"/repos/{repo}/actions/workflows/{workflow}/runs?branch=main&created={created}&per_page=50", token)
    # A cancelled run did no work: a pending run in a shared concurrency group is cancelled
    # when a newer one queues (daily-refresh and refresh-diagnostics share korea-data).
    return sum(1 for run in result.get("workflow_runs", []) if run.get("conclusion") != "cancelled")


def dispatch(repo, workflow, token):
    api("POST", f"/repos/{repo}/actions/workflows/{workflow}/dispatches", token, {"ref": "main"})


def check(repo, token, now=None, dry_run=False, count=runs_since, start=dispatch, errors=None):
    """Workflows started; a failure on one workflow is recorded in `errors` and never skips the others."""
    now = now or datetime.now(timezone.utc)
    started = []
    for workflow in WATCHED:
        slot = latest_slot(crons(workflow), now)
        if slot is None:
            continue
        try:
            if count(repo, workflow, slot, token):
                print(f"{workflow}: ran after its {slot:%m-%d %H:%M}Z slot.")
                continue
            print(f"::warning::{workflow}: no run since its {slot:%m-%d %H:%M}Z slot; "
                  f"{'would start' if dry_run else 'starting'} it now.")
            if not dry_run:
                start(repo, workflow, token)
            started.append(workflow)
        except (OSError, ValueError) as exc:  # HTTPError/URLError are OSErrors
            # 404: the workflow is not on the default branch yet (e.g. before its PR is merged).
            print(f"::warning::{workflow}: could not check or start it ({exc}).")
            if errors is not None:
                errors.append(workflow)
    return started


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        raise SystemExit("GH_TOKEN and GITHUB_REPOSITORY are required")
    errors = []
    check(repo, token, dry_run=args.dry_run, errors=errors)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
