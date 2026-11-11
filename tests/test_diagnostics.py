import unittest
from datetime import date, timedelta

from qsignals.diagnostics import (
    PRE_WARNING_DAYS,
    diagnose_event,
    large_drops,
    unlisted_drops,
)
from qsignals.report import _Probe
from qsignals.scores import ScoreRow
from qsignals.calendar import load_sessions


def make_rows(n=30, risk=0.1, msi=0.0, threshold=1.0):
    days = [d for d in load_sessions() if d >= "2026-01-02"][:n]
    return [
        ScoreRow(
            date=days[i],
            kospi200_close=100.0,
            risk_v1=risk,
            msi=msi,
            stress_threshold=threshold,
            record_type="OOS_WALK_FORWARD",
        )
        for i in range(n)
    ]


def replace(rows, i, **changes):
    r = rows[i]
    rows[i] = ScoreRow(**{**r.__dict__, **changes})


def probe(rows, i):
    return _Probe(event_id="E", date=rows[i].date)


class DiagnoseEventTest(unittest.TestCase):
    def test_entire_missing_session_is_incomplete(self):
        rows = make_rows()
        event = probe(rows, 20)
        missing = rows[17].date
        del rows[17]
        d = diagnose_event(event, rows)
        self.assertEqual(d.verdict, "INCOMPLETE")
        self.assertEqual(d.missing_pre_sessions, missing)

    def test_missing_previous_session_is_not_a_daily_return(self):
        rows = make_rows()
        event = probe(rows, 20)
        replace(rows, 20, kospi200_close=80.0)
        del rows[19]
        d = diagnose_event(event, rows)
        self.assertIsNone(d.kospi200_return_pct)
        self.assertIsNone(d.risk_prev)
        self.assertEqual(d.verdict, "INCOMPLETE")

    def test_no_warning_and_no_stress_is_missed(self):
        rows = make_rows()
        d = diagnose_event(probe(rows, 20), rows)
        self.assertEqual(d.verdict, "MISSED")
        self.assertEqual(d.warning_days_pre, 0)
        self.assertEqual(d.stress_days_pre, 0)

    def test_warning_inside_window_counts(self):
        rows = make_rows()
        replace(rows, 17, risk_v1=0.6)
        d = diagnose_event(probe(rows, 20), rows)
        self.assertEqual(d.verdict, "WARNED")
        self.assertEqual(d.warning_days_pre, 1)
        self.assertEqual(d.warning_streak_prev, 0)
        self.assertAlmostEqual(d.max_risk_pre, 0.6)

    def test_threshold_is_inclusive(self):
        rows = make_rows()
        replace(rows, 19, risk_v1=0.5)
        self.assertEqual(diagnose_event(probe(rows, 20), rows).verdict, "WARNED")

    def test_warning_just_outside_window_is_ignored(self):
        rows = make_rows()
        replace(rows, 20 - PRE_WARNING_DAYS - 1, risk_v1=0.9)
        self.assertEqual(diagnose_event(probe(rows, 20), rows).verdict, "MISSED")

    def test_event_day_score_is_not_an_advance_warning(self):
        rows = make_rows()
        replace(rows, 20, risk_v1=0.95)
        d = diagnose_event(probe(rows, 20), rows)
        self.assertEqual(d.verdict, "MISSED")
        self.assertAlmostEqual(d.risk_on_event, 0.95)

    def test_prior_stress_takes_precedence_over_warning(self):
        rows = make_rows(risk=0.9)
        replace(rows, 18, msi=1.2)
        d = diagnose_event(probe(rows, 20), rows)
        self.assertEqual(d.verdict, "IN_STRESS")
        self.assertEqual(d.stress_days_pre, 1)

    def test_stress_outside_five_day_window_is_ignored(self):
        rows = make_rows()
        replace(rows, 14, msi=1.5)
        self.assertEqual(diagnose_event(probe(rows, 20), rows).verdict, "MISSED")

    def test_streak_counts_consecutive_days_ending_yesterday(self):
        rows = make_rows()
        for i in (15, 17, 18, 19):
            replace(rows, i, risk_v1=0.7)
        d = diagnose_event(probe(rows, 20), rows)
        self.assertEqual(d.warning_streak_prev, 3)
        self.assertEqual(d.warning_days_pre, 4)

    def test_missing_score_in_window_is_incomplete(self):
        rows = make_rows()
        replace(rows, 16, risk_v1=None, record_type="NO_SCORE")
        d = diagnose_event(probe(rows, 20), rows)
        self.assertEqual(d.verdict, "INCOMPLETE")
        self.assertIsNone(d.max_risk_pre)

    def test_missing_msi_in_stress_window_is_incomplete(self):
        rows = make_rows()
        replace(rows, 19, msi=None)
        self.assertEqual(diagnose_event(probe(rows, 20), rows).verdict, "INCOMPLETE")

    def test_short_history_is_incomplete(self):
        rows = make_rows()
        self.assertEqual(diagnose_event(probe(rows, 3), rows).verdict, "INCOMPLETE")

    def test_date_outside_series_is_no_data(self):
        rows = make_rows()
        d = diagnose_event(_Probe(event_id="E", date="2027-01-01"), rows)
        self.assertEqual(d.verdict, "NO_DATA")

    def test_return_uses_previous_trading_row(self):
        rows = make_rows()
        replace(rows, 20, kospi200_close=90.0)
        self.assertAlmostEqual(diagnose_event(probe(rows, 20), rows).kospi200_return_pct, -10.0)

    def test_window_record_types_reported(self):
        rows = make_rows()
        replace(rows, 19, record_type="RETROSPECTIVE_INFERENCE")
        d = diagnose_event(probe(rows, 20), rows)
        self.assertEqual(d.window_record_types, "OOS_WALK_FORWARD;RETROSPECTIVE_INFERENCE")


class LargeDropsTest(unittest.TestCase):
    def test_finds_drops_and_skips_missing_prices(self):
        rows = make_rows(n=6)
        replace(rows, 2, kospi200_close=94.0)  # -6%
        replace(rows, 3, kospi200_close=None)
        replace(rows, 4, kospi200_close=50.0)  # previous price missing
        replace(rows, 5, kospi200_close=47.6)  # -4.8%
        drops = large_drops(rows, -5.0)
        self.assertEqual([d for d, _ in drops], [rows[2].date])

    def test_start_date_filter_and_unlisted(self):
        rows = make_rows(n=6)
        replace(rows, 1, kospi200_close=90.0)
        replace(rows, 4, kospi200_close=80.0)
        drops = large_drops(rows, -5.0, start_date=rows[2].date)
        self.assertEqual([d for d, _ in drops], [rows[4].date])
        self.assertEqual(unlisted_drops(drops, [_Probe(event_id="E", date=rows[4].date)]), [])


if __name__ == "__main__":
    unittest.main()
