import csv
import json
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

    def test_us_rows_and_price_column(self):
        global_markets = {"korea": [], "us": [{"date": "2026-09-21", "price": 660.0, "risk": 0.3, "msi": 0.2, "threshold": 1.3}]}
        operational = {"markets": {"us": {"history": [
            {"date": "2026-09-21", "risk": 0.9, "msi": 0.1, "threshold": 1.3, "recordType": "RETROSPECTIVE_INFERENCE"},
            {"date": "2026-11-06", "risk": 0.945, "msi": 1.14, "threshold": 1.29, "recordType": "OPERATIONAL"},
        ]}}}
        rows = build_rows(global_markets, operational, "us")
        self.assertEqual([r.record_type for r in rows], ["OOS_WALK_FORWARD", "OPERATIONAL"])
        self.assertEqual(rows[0].risk_v1, 0.3)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "us.csv"
            write_scores(rows, path, "us")
            self.assertTrue(path.read_text(encoding="utf-8").startswith("date,spy_close,"))
            self.assertEqual(read_scores(path, "us"), rows)
            with self.assertRaises(ValueError):
                read_scores(path)  # a US file is not a Korea file

    def test_import_keeps_previous_us_file_when_skipped(self):
        from qsignals.import_scores import import_scores
        point = {"date": "2026-09-21", "price": 1.0, "risk": 0.3, "msi": 0.2, "threshold": 1.3}
        gm = {"korea": [point], "us": [point]}
        op = {"runId": "r", "markets": {m: {"history": [], "modelSha256": m, "trainingCutoff": "2026-09-16"} for m in ("korea", "us")}}
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "src", Path(d) / "out"
            (src / "frontend/public/data").mkdir(parents=True)
            (src / "frontend/public/data/global-markets.json").write_text(json.dumps(gm), encoding="utf-8")
            (src / "frontend/public/data/operational-markets.json").write_text(json.dumps(op), encoding="utf-8")
            first = import_scores(src, out)
            self.assertEqual(set(first["markets"]), {"korea", "us"})
            us_before = (out / "us_scores.csv").read_bytes()
            second = import_scores(src, out, markets=("korea",))
            self.assertTrue(second["markets"]["us"]["kept_from_previous_import"])
            self.assertEqual((out / "us_scores.csv").read_bytes(), us_before)
            korea_before = (out / "korea_scores.csv").read_bytes()
            third = import_scores(src, out, {"source_git_commit": "new", "refresh": {}}, markets=("us",))  # stale Korea run
            self.assertTrue(third["markets"]["korea"]["kept_from_previous_import"])
            self.assertEqual(third["markets"]["us"]["source_git_commit"], "new")
            self.assertIsNone(third["markets"]["korea"]["source_git_commit"])  # kept file keeps its own source
            self.assertIsNone(third["source_git_commit"])  # top level describes korea_scores.csv
            self.assertEqual(third["refresh"], {})
            self.assertEqual((out / "korea_scores.csv").read_bytes(), korea_before)
            with self.assertRaises(ValueError):
                import_scores(src, Path(d) / "fresh", markets=("us",))  # no Korea import yet

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
