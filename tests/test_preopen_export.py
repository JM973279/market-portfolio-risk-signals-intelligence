"""Checks for the Korea pre-open reference export. Standard library only, no network."""
import json
import unittest
from pathlib import Path

from qsignals import preopen_export
from qsignals.overnight import Overnight
from qsignals.overnight_eval import DESIGN_END

ROOT = Path(__file__).resolve().parents[1]


class Buckets(unittest.TestCase):
    def test_edges_are_upper_inclusive(self):
        self.assertEqual(preopen_export.bucket_of(-0.03), "le_-3")
        self.assertEqual(preopen_export.bucket_of(-0.0299), "-3_-1")
        self.assertEqual(preopen_export.bucket_of(0.01), "-1_1")
        self.assertEqual(preopen_export.bucket_of(0.03), "1_3")
        self.assertEqual(preopen_export.bucket_of(0.0301), "gt_3")


class Context(unittest.TestCase):
    def test_holdout_sessions_are_never_counted(self):
        aligned = {
            "2025-12-29": Overnight("2025-12-29", "2025-12-26", {"EWY": -0.05}),
            "2025-12-30": Overnight("2025-12-30", "2025-12-29", {"EWY": 0.0}),
            "2026-01-02": Overnight("2026-01-02", "2025-12-31", {"EWY": -0.05}),
        }
        kospi = {"2025-12-29": -0.03, "2025-12-30": 0.01, "2026-01-02": -0.04}
        ctx = preopen_export.context(aligned, kospi)
        self.assertEqual(ctx["period"], {"first": "2025-12-29", "last": "2025-12-30"})
        self.assertEqual(ctx["all"]["sessions"], 2)
        low = next(b for b in ctx["buckets"] if b["key"] == "le_-3")
        self.assertEqual((low["sessions"], low["drop_share"]), (1, 1.0))

    def test_returns_need_consecutive_calendar_sessions(self):
        class Row:
            def __init__(self, day, close):
                self.date, self.kospi200_close = day, close
        rows = [Row("2025-01-02", 100.0), Row("2025-01-06", 110.0)]  # 01-03 missing
        out = preopen_export.kospi_returns(rows, ("2025-01-02", "2025-01-03", "2025-01-06"))
        self.assertEqual(out, {})


class Published(unittest.TestCase):
    def test_committed_export_matches_stored_overnight_prices(self):
        path = ROOT / "frontend/public/data/korea-preopen.json"
        export = json.loads(path.read_text(encoding="utf-8"))
        provenance = json.loads((ROOT / "data/input/overnight_provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(export["source"]["sha256"], provenance["sha256"],
                         "korea-preopen.json is stale; run python3 -m qsignals.preopen_export")
        self.assertIs(export["is_forecast"], False)
        self.assertLessEqual(export["context"]["period"]["last"], DESIGN_END)
        self.assertEqual(export["history"][0], export["latest"])
        # Returns only: no closes or other price levels leave the repository through the site.
        text = path.read_text(encoding="utf-8")
        for word in ("close", "price"):
            self.assertNotIn(f'"{word}', text)

    def test_export_is_reproducible(self):
        path = ROOT / "frontend/public/data/korea-preopen.json"
        self.assertEqual(preopen_export.render(preopen_export.build()), path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
