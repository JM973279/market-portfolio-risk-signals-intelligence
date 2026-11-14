"""The KRX calendar extension never rewrites published sessions (no library or network here)."""
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts import update_krx_calendar as cal

ROOT = Path(__file__).resolve().parent.parent


def weekdays(start, end):
    day, out = date.fromisoformat(start), []
    while day <= date.fromisoformat(end):
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def fake_library(start, end):
    return weekdays(start, end), "test"


class KrxCalendarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        self.csv, self.meta = folder / "xkrx_sessions.csv", folder / "provenance.json"
        data = cal.render([d for d in weekdays("2026-11-02", "2026-12-31") if d not in ("2026-12-31",)])
        self.csv.write_bytes(data)
        self.meta.write_text(json.dumps({"start": "2026-11-02", "end": "2026-12-31", "sha256": hashlib.sha256(data).hexdigest(),
                                         "additional_closures": {"2026-12-31": "연말 휴장"}}))
        for name, value in (("CALENDAR", self.csv), ("PROVENANCE", self.meta)):
            patcher = patch.object(cal, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, *argv, today=None):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            code = cal.main(list(argv), today=today, sessions_source=fake_library)
        return code, out.getvalue()

    def test_check_rebuilds_the_committed_file(self):
        self.assertEqual(self.run_main("--check")[0], 0)
        self.csv.write_bytes(self.csv.read_bytes().replace(b"2026-11-03\n", b""))
        self.assertEqual(self.run_main("--check")[0], 1)

    def test_extends_to_next_year_end_only_when_due(self):
        before = self.csv.read_bytes()
        self.assertEqual(self.run_main("--extend-within-days", "90", today=date(2026, 9, 1))[0], 0)
        self.assertEqual(self.csv.read_bytes(), before)  # 121 days left: not due yet
        code, out = self.run_main("--extend-within-days", "90", today=date(2026, 11, 14))
        self.assertEqual(code, 0)
        meta = json.loads(self.meta.read_text())
        self.assertEqual(meta["end"], "2027-12-31")
        self.assertTrue(self.csv.read_bytes().startswith(before))  # published sessions unchanged
        self.assertEqual(meta["sha256"], hashlib.sha256(self.csv.read_bytes()).hexdigest())
        self.assertIn("2027-12-30\n", self.csv.read_text())
        self.assertNotIn("2026-12-31\n", self.csv.read_text())  # additional closure still applied
        self.assertIn("closure notice", out)

    def test_refuses_to_change_published_sessions(self):
        def changed(start, end):
            days, version = fake_library(start, end)
            return [d for d in days if d != "2026-11-03"], version
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = cal.main(["--extend-within-days", "90"], today=date(2026, 11, 14), sessions_source=changed)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(self.meta.read_text())["end"], "2026-12-31")

    def test_committed_calendar_matches_its_provenance(self):
        meta = json.loads((ROOT / "data/calendar/provenance.json").read_text(encoding="utf-8"))
        data = (ROOT / "data/calendar/xkrx_sessions.csv").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), meta["sha256"])
        self.assertTrue(data.startswith(b"date\n") and data.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
