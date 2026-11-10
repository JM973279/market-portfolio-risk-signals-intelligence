"""Checks for the Korea historical scenario library export. Read-only; never runs a model."""
import json
import unittest
from pathlib import Path

from market_engine.scenarios import build_korea_library as library

ROOT = Path(__file__).resolve().parents[1]
NOTE_CODES = {"price_missing", "window_incomplete", "trough_at_window_end", "source_unverified", "window_overlaps"}


class KoreaScenarioLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = library.OUTPUT_PATH.read_text()
        cls.export = json.loads(cls.text)
        cls.snapshot = json.loads(library.GLOBAL_PATH.read_text())
        cls.curated = json.loads(library.EPISODES_PATH.read_text())

    def test_export_is_current(self):
        self.assertEqual(library.render(library.build()), self.text)

    def test_no_forecast_and_no_non_finite_values(self):
        self.assertIs(self.export["is_forecast"], False)
        self.assertNotIn("NaN", self.text)
        self.assertNotIn("Infinity", self.text)

    def test_curated_fields_are_copied_unchanged(self):
        self.assertEqual([e["id"] for e in self.export["episodes"]], [e["id"] for e in self.curated["episodes"]])
        for out, src in zip(self.export["episodes"], self.curated["episodes"]):
            for key, value in src.items():
                self.assertEqual(out[key], value, f"{src['id']}.{key}")

    def test_categories_notes_and_sources(self):
        for e in self.export["episodes"]:
            self.assertIn(e["category"], self.export["categories"])
            self.assertTrue(set(e["notes"]) <= NOTE_CODES, e["id"])
            self.assertEqual("source_unverified" in e["notes"], e["source"] is None)
            self.assertEqual("window_overlaps" in e["notes"], bool(e["overlaps"]))

    def test_onset_return_matches_stored_prices(self):
        prices = [(p["date"], p["price"]) for p in self.snapshot["korea"] if p["price"] is not None]
        index = {d: i for i, (d, _) in enumerate(prices)}
        for e in self.export["episodes"]:
            m = e["metrics"]
            if m is None:
                self.assertIn("price_missing", e["notes"])
                continue
            i = index[e["onset"]]
            self.assertEqual(m["reference_date"], prices[i - 1][0])
            self.assertAlmostEqual(m["onset_return"], prices[i][1] / prices[i - 1][1] - 1, places=6)
            self.assertLessEqual(m["max_drawdown"], m["onset_return"] + 1e-9)
            window = [p for _, p in prices[i:i + library.WINDOW_SESSIONS]]
            self.assertAlmostEqual(m["max_drawdown"], min(window) / prices[i - 1][1] - 1, places=6)

    def test_verdict_boundaries(self):
        self.assertEqual(library.verdict(None), "no_data")
        self.assertEqual(library.verdict(0.5), "warned")
        self.assertEqual(library.verdict(0.4999), "borderline")
        self.assertEqual(library.verdict(0.4), "borderline")
        self.assertEqual(library.verdict(0.3999), "missed")

    def test_historical_oos_values_take_precedence(self):
        by_date = {p["date"]: p for p in self.snapshot["korea"]}
        for e in self.export["episodes"]:
            model = e["model"]
            if model["origin"] == "historical_oos":
                self.assertEqual(model["prior_risk"], by_date[model["prior_date"]]["risk"])
                self.assertEqual(model["verdict"], library.verdict(model["prior_risk"]))

    def test_summary_counts_match_episodes(self):
        total = sum(row["episodes"] for row in self.export["summary"])
        self.assertEqual(total, len(self.export["episodes"]))
        for row in self.export["summary"]:
            group = [e for e in self.export["episodes"] if e["category"] == row["category"]]
            self.assertEqual(row["with_prices"], sum(e["metrics"] is not None for e in group))
            self.assertEqual(row["warned"], sum(e["model"]["verdict"] == "warned" for e in group))

    def test_invalid_curated_input_is_rejected(self):
        bad = json.loads(json.dumps(self.curated))
        bad["episodes"][0]["category"] = "not_a_category"
        with self.assertRaises(ValueError):
            library.validate(bad)
        bad = json.loads(json.dumps(self.curated))
        bad["episodes"][0]["name"]["ko"] = ""
        with self.assertRaises(ValueError):
            library.validate(bad)


if __name__ == "__main__":
    unittest.main()
