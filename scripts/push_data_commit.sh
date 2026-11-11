#!/usr/bin/env bash
# Two independent data workflows write disjoint paths on main. Keep both commits.
set -euo pipefail
for attempt in 1 2 3; do
  git fetch origin main
  git rebase origin/main
  if git push origin HEAD:main; then
    exit 0
  fi
  echo "main advanced during data publication; retry ${attempt}/3" >&2
done
echo 'Could not publish data after three attempts; no force push was used.' >&2
exit 1
