#!/usr/bin/env bash
# Create the separate interpreter qsignals.refresh uses to run the deployed
# repo's frozen pipeline. Versions come from that repo's pinned
# market_engine/operations/requirements.txt; nothing is installed into the
# host python3 or into either repository.
#
#   scripts/setup_inference_env.sh [DEPLOYED_REPO] [VENV]
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
source_root="${1:-$here/../market-portfolio-risk-intelligence}"
venv="${2:-$HOME/.venvs/mpri-inference}"
requirements="$source_root/market_engine/operations/requirements.txt"
[ -f "$requirements" ] || { echo "not found: $requirements" >&2; exit 1; }

if python3 -c "import ensurepip" 2>/dev/null; then
  python3 -m venv "$venv"
else
  # Ubuntu without python3-venv: bootstrap pip from its official PyPI wheel.
  python3 -m venv --without-pip "$venv"
  tmp="$(mktemp -d)"
  url="$(python3 -c "import json,urllib.request;d=json.load(urllib.request.urlopen('https://pypi.org/pypi/pip/json'));print(next(u['url'] for u in d['urls'] if u['packagetype']=='bdist_wheel'))")"
  wheel="$tmp/${url##*/}"
  python3 -c "import sys,urllib.request;urllib.request.urlretrieve(sys.argv[1],sys.argv[2])" "$url" "$wheel"
  "$venv/bin/python" "$wheel/pip" install -q --disable-pip-version-check "$wheel"
  rm -rf "$tmp"
fi
"$venv/bin/pip" install -q --disable-pip-version-check -r "$requirements"
"$venv/bin/python" -c "import pandas, sklearn, xgboost, exchange_calendars; print('ready:', '$venv')"
