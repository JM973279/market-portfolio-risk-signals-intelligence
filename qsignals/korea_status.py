"""Publish a verified collection delay without replacing published scores."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from qsignals.export_frontend import check_block
from qsignals.scores import read_scores


def save_delayed_status(operational, output_dir):
    candidate = operational["markets"]["korea"]
    if (candidate.get("status") != "DELAYED" or not candidate.get("historicalParity")
            or not candidate.get("inferenceSucceeded")):
        return False
    path = Path(output_dir) / "operational/korea.json"
    if not path.exists():
        return False
    saved = json.loads(path.read_text(encoding="utf-8"))
    rows = read_scores(Path(output_dir) / "korea_scores.csv")
    check_block("korea", saved["block"], rows)
    # Every published inference must still be reproduced. Extra candidate dates
    # are not published here: only CURRENT imports can replace Korea scores.
    published = saved["block"].get("history", [])
    verified = {p["date"]: p for p in candidate.get("history", [])}
    for point in published:
        new = verified.get(point["date"], {})
        if any(point.get(k) != new.get(k) for k in ("risk", "msi", "threshold")):
            raise ValueError("Delayed Korea history differs from published scores")
    last = saved["block"].get("lastValid")
    due = candidate.get("expectedDate")
    if not last or not due or last["date"] >= due:
        return False  # never move the expectation or displayed score backwards
    if saved["block"].get("expectedDate", "") > due:
        return False
    # Retain score provenance separately from this run's fresh collection status.
    saved["scoreRunId"] = saved.get("scoreRunId", saved["runId"])
    saved["collectionAdapter"] = operational.get("collectionAdapter")
    saved["runId"] = operational["runId"]
    saved["generatedAt"] = operational["generatedAt"]
    saved["block"] = {**saved["block"], "status": "DELAYED", "current": None,
                      "expectedDate": due, "series": candidate["series"],
                      "availability": candidate.get("availability", []),
                      "availabilityOrigin": candidate.get("availabilityOrigin"),
                      "reason": candidate.get("reason")}
    # Atomic status update. CSV, prices and their original provenance stay byte-identical.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as f:
        temporary = Path(f.name)
        json.dump(saved, f, ensure_ascii=False, indent=1, allow_nan=False)
        f.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True
