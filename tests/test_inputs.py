import csv
import tempfile
import unittest
from pathlib import Path

from qsignals.diagnostics import VERDICTS, diagnose_all
from qsignals.events import CSV_FIELDS, read_events
from qsignals.scores import ScoreRow, build_rows, read_scores, validate_rows, write_scores

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data/events/kospi_2026_events.csv"
SCORES = ROOT / "data/input/korea_scores.csv"


def event_record(**changes):
    rec = {
        "event_id": "KOSPI-20260304",
        "date": "2026-03-04",
        "index_name": "KOSPI",
        "reported_close": "5093.54",
        "reported_change_pct": "-12.06",
        "intraday_note": "",
        "market_halt": "",
        "trigger_primary": "geopolitics",
        "trigger_secondary": "",
        "trigger_summary": "test",
        "amplifiers": "foreign_selling",
        "source_urls": "https://example.org/a",
        "source_quality": "news",
        "basis": "post_hoc_news",
        "recorded_at": "2026-11-10",
    }
    rec.update(changes)
    return rec


def write_events(records):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
    writer = csv.DictWriter(tmp, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(records)
    tmp.close()
    return Path(tmp.name)


class EventFileTest(unittest.TestCase):
    def test_bundled_events_are_valid(self):
        events = read_events(EVENTS)
        self.assertEqual(len(events), 10)
        self.assertTrue(all(e.basis == "post_hoc_news" for e in events))

    def test_rejections(self):
        cases = {
            "unknown trigger": event_record(trigger_primary="aliens"),
            "unknown amplifier": event_record(amplifiers="vibes"),
            "unsourced with url": event_record(source_quality="unsourced"),
            "sourced without url": event_record(source_urls=""),
            "http url": event_record(source_urls="http://example.org"),
            "recorded before event": event_record(recorded_at="2026-03-01"),
            "same-day log recorded later": event_record(basis="same_day_log"),
            "secondary repeats primary": event_record(trigger_secondary="geopolitics"),
            "no move": event_record(reported_close="", reported_change_pct=""),
            "unknown halt": event_record(market_halt="CB;halt"),
            "impossible date": event_record(date="2026-02-30"),
            "NaN close": event_record(reported_close="nan"),
            "infinite return": event_record(reported_change_pct="inf"),
            "negative close": event_record(reported_close="-1"),
            "empty host": event_record(source_urls="https://"),
        }
        for name, rec in cases.items():
            with self.subTest(name):
                path = write_events([rec])
                try:
                    with self.assertRaises(ValueError):
                        read_events(path)
                finally:
                    path.unlink()

    def test_duplicate_ids_rejected(self):
        path = write_events([event_record(), event_record(date="2026-03-05")])
        try:
            with self.assertRaises(ValueError):
                read_events(path)
        finally:
            path.unlink()


class ScoreImportTest(unittest.TestCase):
    def test_oos_takes_precedence_and_operational_fills_later_dates(self):
        global_markets = {
            "korea": [
                {"date": "2026-09-16", "price": 100.0, "risk": 0.2, "msi": 0.1, "threshold": 1.0},
                {"date": "2026-09-17", "price": 101.0, "risk": None, "msi": 0.3, "threshold": 1.0},
            ]
        }
        operational = {
            "markets": {
                "korea": {
                    "history": [
                        {"date": "2026-09-16", "risk": 0.9, "msi": 9.0, "threshold": 1.0, "recordType": "OPERATIONAL"},
                        {"date": "2026-09-17", "risk": 0.4, "msi": 0.3, "threshold": 1.0, "recordType": "RETROSPECTIVE_INFERENCE"},
                        {"date": "2026-09-18", "risk": 0.5, "msi": 0.2, "threshold": 1.0, "recordType": "OPERATIONAL"},
                    ]
                }
            }
        }
        rows = build_rows(global_markets, operational)
        self.assertEqual([r.record_type for r in rows], ["OOS_WALK_FORWARD", "RETROSPECTIVE_INFERENCE", "OPERATIONAL"])
        self.assertEqual(rows[0].risk_v1, 0.2)
        self.assertEqual(rows[1].kospi200_close, 101.0)
        self.assertIsNone(rows[2].kospi200_close)

    def test_round_trip(self):
        rows = [ScoreRow("2026-01-02", 100.5, 0.25, -0.1, 1.0, "OOS_WALK_FORWARD"), ScoreRow("2026-01-05", None, None, None, None, "NO_SCORE")]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.csv"
            write_scores(rows, path)
            self.assertEqual(read_scores(path), rows)

    def test_validation(self):
        bad = {
            "risk above 1": [ScoreRow("2026-01-02", 1.0, 1.2, 0.0, 1.0, "OOS_WALK_FORWARD")],
            "unsorted": [ScoreRow("2026-01-03", 1.0, 0.1, 0.0, 1.0, "OOS_WALK_FORWARD"), ScoreRow("2026-01-02", 1.0, 0.1, 0.0, 1.0, "OOS_WALK_FORWARD")],
            "score without type": [ScoreRow("2026-01-02", 1.0, 0.1, 0.0, 1.0, "NO_SCORE")],
            "unknown type": [ScoreRow("2026-01-02", 1.0, 0.1, 0.0, 1.0, "BACKFIT")],
            "impossible date": [ScoreRow("2026-02-30", 1.0, 0.1, 0.0, 1.0, "OOS_WALK_FORWARD")],
            "nan price": [ScoreRow("2026-01-02", float("nan"), 0.1, 0.0, 1.0, "OOS_WALK_FORWARD")],
            "nan MSI": [ScoreRow("2026-01-02", 1.0, 0.1, float("nan"), 1.0, "OOS_WALK_FORWARD")],
        }
        for name, rows in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                validate_rows(rows)


@unittest.skipUnless(SCORES.exists(), "run python3 -m qsignals.import_scores first")
class BundledDataTest(unittest.TestCase):
    def test_every_event_gets_a_known_verdict(self):
        rows = read_scores(SCORES)
        diagnoses = diagnose_all(read_events(EVENTS), rows)
        self.assertEqual(len(diagnoses), 10)
        self.assertTrue(all(d.verdict in VERDICTS for d in diagnoses))


if __name__ == "__main__":
    unittest.main()
