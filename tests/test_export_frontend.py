import json
import tempfile
import unittest
from pathlib import Path

from qsignals.export_frontend import build_markets, check_block
from qsignals.scores import MARKETS, ScoreRow, write_scores


def rows():
    return [ScoreRow("2026-09-16", 100.0, 0.2, 0.1, 1.0, "OOS_WALK_FORWARD"),
            ScoreRow("2026-11-09", None, 0.47, 1.06, 1.11, "RETROSPECTIVE_INFERENCE")]


def block(**point):
    base = {"date": "2026-11-09", "price": None, "risk": 0.47, "msi": 1.06, "threshold": 1.11}
    return {"history": [{**base, **point}]}


class CheckBlockTest(unittest.TestCase):
    def test_matching_block_passes(self):
        check_block("korea", block(), rows())

    def test_value_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            check_block("korea", block(risk=0.48), rows())

    def test_date_outside_csv_fails(self):
        with self.assertRaisesRegex(ValueError, "not in"):
            check_block("korea", {"history": block()["history"] + [{"date": "2026-11-10", "risk": 0.5}]}, rows())

    def test_csv_row_missing_from_block_fails(self):
        with self.assertRaisesRegex(ValueError, "missing from the status block"):
            check_block("korea", {"history": []}, rows())


class MarketIndependenceTest(unittest.TestCase):
    def write(self, directory, market, block):
        (directory / "operational").mkdir(exist_ok=True)
        (directory / "operational" / f"{market}.json").write_text(
            json.dumps({"runId": f"{market}-new", "generatedAt": "2026-11-14T00:00:00Z", "block": block}))
        write_scores(rows(), directory / f"{market}_scores.csv", *([] if market == "korea" else [market]))

    def test_a_failed_market_keeps_its_previous_block_and_the_other_is_exported(self):
        previous = {"generatedAt": "2026-11-13T00:00:00Z", "markets": {m: {"history": [], "old": True} for m in MARKETS}}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.write(directory, "korea", block(risk=0.99))  # fails its check
            self.write(directory, "us", block())
            export, errors = build_markets(directory, previous)
        self.assertEqual(set(errors), {"korea"})
        self.assertTrue(export["markets"]["korea"]["old"])
        self.assertEqual(export["markets"]["us"], block())

    def test_no_previous_block_means_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.write(directory, "us", block())
            export, errors = build_markets(directory, None)
        self.assertIsNone(export)
        self.assertEqual(set(errors), {"korea"})


if __name__ == "__main__":
    unittest.main()
