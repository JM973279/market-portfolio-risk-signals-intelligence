"""Published scores never move backwards; per-market dates for commit messages."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qsignals.import_scores import import_data, import_us, publication_check
from qsignals.scores import ScoreRow, read_scores, write_scores
from scripts.published_dates import published_dates
from tests.test_refresh import payloads, xml_prices


def rows(last="2026-01-13", label="OPERATIONAL", price=None):
    out = [ScoreRow("2026-01-12", 100.0, 0.2, 0.1, 1.0, "OOS_WALK_FORWARD")]
    if last >= "2026-01-13":
        out.append(ScoreRow("2026-01-13", price, 0.3, 0.2, 1.0, label))
    return out


class PublicationCheckTest(unittest.TestCase):
    def check(self, published, candidate):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "korea_scores.csv"
            write_scores(published, path)
            return publication_check(candidate, path)

    def test_rules(self):
        self.assertEqual(self.check(rows(), rows(last="2026-01-12")), "older_than_published")
        self.assertEqual(self.check(rows(), rows(label="RETROSPECTIVE_INFERENCE")), "same_date_different_scores")
        self.assertIsNone(self.check(rows(), rows(price=101.0)))  # price-only update on the same date
        newer = rows(label="RETROSPECTIVE_INFERENCE") + [ScoreRow("2026-01-14", None, 0.4, 0.2, 1.0, "OPERATIONAL")]
        self.assertIsNone(self.check(rows(), newer))  # a newer last date always passes
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(publication_check(rows(), Path(d) / "missing.csv"))


class ImportGuardTest(unittest.TestCase):
    def test_korea_import_refuses_older_scores(self):
        # Review reproduction: publish through day 7, then re-import data ending at day 6.
        days, data = payloads()
        older = copy.deepcopy(data)
        older["operational_markets"]["markets"]["korea"]["history"] = []
        raw = xml_prices(days)
        meta = {"provider": "test", "sha256": hashlib.sha256(raw).hexdigest(), "last_date": days[-1], "retrieved_at": "t"}
        prices = {day: 100. for day in days}
        with tempfile.TemporaryDirectory() as temp, \
                patch("qsignals.import_scores.latest_closed_session", return_value=days[-1]), \
                patch("qsignals.import_scores.fetch_prices", return_value=(prices, raw, meta)):
            first = import_data(data, {}, {}, temp)
            before = (Path(temp) / "korea_scores.csv").read_bytes()
            second = import_data(older, {}, {}, temp)
            self.assertEqual(second["publication"]["reason"], "older_than_published")
            self.assertEqual(second["last_risk_date"], first["last_risk_date"])
            self.assertEqual((Path(temp) / "korea_scores.csv").read_bytes(), before)

    def test_us_import_refuses_older_scores(self):
        point = {"date": "2026-09-21", "price": 660.0, "risk": 0.3, "msi": 0.2, "threshold": 1.3}
        newer = {"global_markets": {"korea": [], "us": [point]}, "operational_markets": {"runId": "r", "markets": {"us": {
            "history": [{"date": "2026-11-06", "risk": .9, "msi": 1.1, "threshold": 1.3, "recordType": "OPERATIONAL"}],
            "status": "DELAYED", "trainingCutoff": "2026-09-16"}}}}
        older = copy.deepcopy(newer)
        older["operational_markets"]["markets"]["us"]["history"] = []
        with tempfile.TemporaryDirectory() as d:
            import_us(newer, {}, {}, d)
            result = import_us(older, {}, {}, d)
            self.assertEqual(result["publication"]["reason"], "older_than_published")
            self.assertEqual(read_scores(Path(d) / "us_scores.csv", "us")[-1].date, "2026-11-06")


class PublishedDatesTest(unittest.TestCase):
    def test_reads_both_provenance_files(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "data/input").mkdir(parents=True)
            (Path(d) / "data/input/provenance.json").write_text(json.dumps({"last_risk_date": "2026-11-10"}))
            self.assertEqual(published_dates(d), {"korea": "2026-11-10", "us": None})
            (Path(d) / "data/input/us_provenance.json").write_text(json.dumps({"last_risk_date": "2026-11-09"}))
            self.assertEqual(published_dates(d), {"korea": "2026-11-10", "us": "2026-11-09"})


if __name__ == "__main__":
    unittest.main()
