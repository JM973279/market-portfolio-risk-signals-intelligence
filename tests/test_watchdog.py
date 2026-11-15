"""Schedule watchdog decisions, against the repository's own cron lines (no network)."""
import io
import unittest
import unittest.mock
from contextlib import redirect_stdout
from datetime import datetime, timezone

from qsignals import watchdog


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class CronTest(unittest.TestCase):
    def test_fields_and_weekdays(self):
        v1 = "7 0,3 * * 2-6"  # 09:07 / 12:07 KST, Tue-Sat
        self.assertTrue(watchdog.matches(v1, utc(2026, 11, 14, 0, 7)))       # Saturday
        self.assertFalse(watchdog.matches(v1, utc(2026, 11, 15, 0, 7)))      # Sunday
        self.assertTrue(watchdog.matches("37 */4 * * *", utc(2026, 11, 14, 20, 37)))
        self.assertFalse(watchdog.matches("37 */4 * * *", utc(2026, 11, 14, 21, 37)))
        self.assertTrue(watchdog.matches("23 1 1,15 * *", utc(2026, 12, 1, 1, 23)))

    def test_latest_slot_respects_the_grace_period(self):
        crons = ["7 0,3 * * 2-6"]
        self.assertEqual(watchdog.latest_slot(crons, utc(2026, 11, 14, 3, 30)), utc(2026, 11, 14, 0, 7))
        self.assertEqual(watchdog.latest_slot(crons, utc(2026, 11, 14, 3, 52)), utc(2026, 11, 14, 3, 7))
        # Sunday and Monday have no slot: Saturday's last slot stays the latest.
        self.assertEqual(watchdog.latest_slot(crons, utc(2026, 11, 16, 12, 0)), utc(2026, 11, 14, 3, 7))

    def test_every_watched_workflow_has_a_parsable_schedule(self):
        for workflow in watchdog.WATCHED:
            lines = watchdog.crons(workflow)
            self.assertTrue(lines, workflow)
            self.assertIsNotNone(watchdog.latest_slot(lines, utc(2026, 11, 20, 12, 0)), workflow)


class RunCountTest(unittest.TestCase):
    def test_cancelled_runs_do_not_count(self):
        runs = {"workflow_runs": [{"conclusion": "cancelled"}, {"conclusion": None}]}
        with unittest.mock.patch.object(watchdog, "api", return_value=runs) as api:
            self.assertEqual(watchdog.runs_since("o/r", "daily-refresh.yml", utc(2026, 11, 14, 3, 7), "t"), 1)
        self.assertIn("created=%3E%3D2026-11-14T03%3A07%3A00Z", api.call_args.args[1])
        with unittest.mock.patch.object(watchdog, "api", return_value={"workflow_runs": [{"conclusion": "cancelled"}]}):
            self.assertEqual(watchdog.runs_since("o/r", "daily-refresh.yml", utc(2026, 11, 14, 3, 7), "t"), 0)


class DecisionTest(unittest.TestCase):
    def run_check(self, ran):
        started = []
        with redirect_stdout(io.StringIO()):
            result = watchdog.check("o/r", "t", now=utc(2026, 11, 14, 5, 29),
                                    count=lambda repo, wf, slot, token: ran(wf),
                                    start=lambda repo, wf, token: started.append(wf))
        return result, started

    def test_starts_only_workflows_without_a_run_since_their_slot(self):
        result, started = self.run_check(lambda wf: wf != "daily-refresh.yml")
        self.assertEqual(result, ["daily-refresh.yml"])
        self.assertEqual(started, ["daily-refresh.yml"])

    def test_one_failing_workflow_does_not_skip_the_others(self):
        import urllib.error
        def count(repo, wf, slot, token):
            if wf == "daily-refresh.yml":
                raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
            return 0
        started, errors = [], []
        with redirect_stdout(io.StringIO()):
            watchdog.check("o/r", "t", now=utc(2026, 11, 14, 5, 29), count=count,
                           start=lambda repo, wf, token: started.append(wf), errors=errors)
        self.assertEqual(errors, ["daily-refresh.yml"])
        self.assertEqual(len(started), len(watchdog.WATCHED) - 1)

    def test_nothing_started_when_every_schedule_ran(self):
        self.assertEqual(self.run_check(lambda wf: True), ([], []))

    def test_dry_run_starts_nothing(self):
        started = []
        with redirect_stdout(io.StringIO()):
            result = watchdog.check("o/r", "t", now=utc(2026, 11, 14, 5, 29), dry_run=True,
                                    count=lambda *a: 0, start=lambda *a: started.append(a))
        self.assertEqual(started, [])
        self.assertEqual(len(result), len(watchdog.WATCHED))


if __name__ == "__main__":
    unittest.main()
