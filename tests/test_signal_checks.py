"""Checks for the pre-registered signal checks. Standard library only, no network."""
import csv
import hashlib
import json
import random
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from qsignals import msi_check, overnight_eval, preopen, signal_checks
from qsignals.calendar import load_sessions
from qsignals.overnight import align, read_overnight
from qsignals.overnight_refresh import build, publish
from qsignals.portfolio_data import PortfolioError
from qsignals.schedule import first_krx_session_after, nearby, read_schedule, upcoming
from qsignals.scores import ScoreRow, read_scores
from qsignals.stats import Logistic, average_precision, block_bootstrap_diff, solve

ROOT = Path(__file__).resolve().parents[1]


def weekdays(start, n):
    out, d = [], date.fromisoformat(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def write_overnight(folder, rows, tickers=("EWY", "^SOX"), next_session=None):
    path, meta_path = Path(folder) / "o.csv", Path(folder) / "o.json"
    with path.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", *tickers])
        for day, closes in rows:
            w.writerow([day, *["" if closes.get(t) is None else repr(closes[t]) for t in tickers]])
    meta = {"tickers": list(tickers), "rows": len(rows), "last_date": rows[-1][0],
            "next_us_session": next_session or rows[-1][0], "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "provider": "test", "first_date": rows[0][0], "missing_sessions": {}}
    meta_path.write_text(json.dumps(meta))
    return path, meta_path


class ScheduleTest(unittest.TestCase):
    def test_committed_schedule_is_valid_and_maps_after_the_us_release(self):
        schedule = read_schedule(ROOT / "data/events/scheduled_us_2026.csv")
        self.assertTrue(schedule)
        for s in schedule:
            self.assertGreater(s.krx_session, s.us_date)
        cpi = next(s for s in schedule if s.event_id == "CPI-20261014")
        self.assertEqual(cpi.krx_session, "2026-10-15")

    def test_friday_release_maps_to_next_krx_session(self):
        self.assertEqual(first_krx_session_after("2026-11-06"), "2026-11-09")

    def test_nearby_and_upcoming_windows(self):
        schedule = read_schedule(ROOT / "data/events/scheduled_us_2026.csv")
        self.assertEqual([s.event_id for s in nearby(schedule, "2026-11-06")], ["ELECTION-20261103"])
        self.assertEqual([s.event_id for s in upcoming(schedule, "2026-11-10", count=1)], ["CPI-20261110"])

    def test_invalid_rows_are_rejected(self):
        header = "event_id,us_date,event_type,description,release_time_et,source_url,verified_at\n"
        for bad in ("X,2026-01-13,EARNINGS,d,08:30,https://a.example,2026-11-11\n",
                    "X,2026-01-13,CPI,d,08:30,http://a.example,2026-11-11\n",
                    "X,2026-01-13,CPI,d,8:30,https://a.example,2026-11-11\n"):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "s.csv"
                path.write_text(header + bad)
                with self.assertRaises(ValueError):
                    read_schedule(path)


class OvernightAlignTest(unittest.TestCase):
    def test_uses_only_the_us_session_strictly_before_the_krx_date(self):
        rows = [("2026-11-04", {"EWY": 100.0}), ("2026-11-05", {"EWY": 110.0}), ("2026-11-06", {"EWY": 99.0})]
        with tempfile.TemporaryDirectory() as tmp:
            o, meta = read_overnight(*write_overnight(tmp, rows, ("EWY",), "2026-11-09"))
            out = align(["2026-11-06", "2026-11-09"], o, meta)
        self.assertEqual(out["2026-11-06"].us_date, "2026-11-05")
        self.assertAlmostEqual(out["2026-11-06"].returns["EWY"], 0.10)
        self.assertEqual(out["2026-11-09"].us_date, "2026-11-06")
        self.assertAlmostEqual(out["2026-11-09"].returns["EWY"], -0.10)

    def test_stale_missing_and_incomplete_sessions_are_not_filled(self):
        rows = [("2026-10-01", {"EWY": 100.0}), ("2026-10-02", {"EWY": None}), ("2026-10-05", {"EWY": 101.0})]
        with tempfile.TemporaryDirectory() as tmp:
            o, meta = read_overnight(*write_overnight(tmp, rows, ("EWY",), "2026-10-06"))
            out = align(["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-20"], o, meta)
        self.assertIsNone(out["2026-10-05"].returns["EWY"])  # previous close missing
        self.assertIsNone(out["2026-10-06"].returns["EWY"])  # base close missing
        self.assertNotIn("2026-10-07", out)  # US session 10-06 not collected yet
        self.assertNotIn("2026-10-20", out)  # stale

    def test_hash_mismatch_is_rejected_and_missing_files_mean_not_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, meta_path = write_overnight(tmp, [("2026-10-01", {"EWY": 1.0})], ("EWY",))
            path.write_text(path.read_text() + "2026-10-02,2.0\n")
            with self.assertRaises(ValueError):
                read_overnight(path, meta_path)
            self.assertEqual(read_overnight(Path(tmp) / "none.csv", meta_path), (None, None))


class OvernightRefreshTest(unittest.TestCase):
    def test_build_keeps_gaps_blank_and_requires_latest_close(self):
        sessions = weekdays("2026-01-05", 200)
        quotes = {"EWY": {d: 100.0 + i for i, d in enumerate(sessions)}, "^SOX": {d: 50.0 for d in sessions}}
        quotes["^SOX"].pop(sessions[10])
        raw, meta = build(sessions, quotes, "2026-12-31")
        lines = raw.decode().splitlines()
        self.assertEqual(lines[11].split(",")[2], "")
        self.assertEqual(meta["missing_sessions"]["^SOX"], [sessions[10]])
        self.assertEqual(meta["sha256"], hashlib.sha256(raw).hexdigest())
        quotes["EWY"].pop(sessions[-1])
        with self.assertRaises(PortfolioError):
            build(sessions, quotes, "2026-12-31")

    def test_low_coverage_is_rejected(self):
        sessions = weekdays("2026-01-05", 100)
        quotes = {"EWY": {d: 1.0 for d in sessions[::2] + [sessions[-1]]}, "^SOX": {d: 1.0 for d in sessions}}
        with self.assertRaises(PortfolioError):
            build(sessions, quotes, "2026-12-31")

    def test_unchanged_publication_keeps_old_timestamp(self):
        sessions = weekdays("2026-01-05", 120)
        quotes = {t: {d: 10.0 for d in sessions} for t in ("EWY", "^SOX")}
        raw, meta = build(sessions, quotes, "2026-12-31")
        with tempfile.TemporaryDirectory() as tmp:
            first = publish(raw, meta, Path(tmp) / "o.csv", Path(tmp) / "o.json")
            second = publish(raw, meta, Path(tmp) / "o.csv", Path(tmp) / "o.json")
            self.assertEqual(first["retrieved_at"], second["retrieved_at"])
            self.assertEqual(read_overnight(Path(tmp) / "o.csv", Path(tmp) / "o.json")[1]["rows"], 120)


class StatsTest(unittest.TestCase):
    def test_average_precision_with_ties(self):
        self.assertAlmostEqual(average_precision([0.9, 0.8, 0.8, 0.1], [1, 0, 1, 0]), 1 / 2 * 1 + 1 / 2 * (2 / 3))
        self.assertIsNone(average_precision([0.1, 0.2], [0, 0]))

    def test_logistic_recovers_direction_and_solve_is_exact(self):
        rng = random.Random(3)
        x = [[rng.gauss(0, 1)] for _ in range(400)]
        y = [1 if v[0] + rng.gauss(0, 0.5) > 1 else 0 for v in x]
        model = Logistic().fit(x, y)
        self.assertGreater(model.coef[1], 0)
        self.assertLess(model.predict([[-2.0]])[0], model.predict([[2.0]])[0])
        self.assertEqual([round(v, 9) for v in solve([[2.0, 1.0], [1.0, 3.0]], [3.0, 5.0])], [0.8, 1.4])

    def test_block_bootstrap_is_deterministic(self):
        groups = [f"m{i // 20}" for i in range(200)]
        y = [1 if i % 10 == 0 else 0 for i in range(200)]
        a = [0.5] * 200
        b = [0.9 if v else 0.1 for v in y]
        self.assertEqual(block_bootstrap_diff(groups, a, b, y, reps=50), block_bootstrap_diff(groups, a, b, y, reps=50))
        self.assertGreater(block_bootstrap_diff(groups, a, b, y, reps=50)[0], 0)


def synthetic_rows(sessions, closes, risk=0.2):
    return [ScoreRow(d, c, risk, 0.0, 1.0, "OOS_WALK_FORWARD") for d, c in zip(sessions, closes)]


class OvernightEvalTest(unittest.TestCase):
    def make(self, informative, n=1100):
        sessions = [d for d in load_sessions() if d >= "2016-09-13"][:n]
        rng = random.Random(11)
        us_days = sorted({(date.fromisoformat(d) - timedelta(days=1)).isoformat() for d in sessions})
        shock = {d: rng.random() < 0.06 for d in us_days}
        closes, price = [], 100.0
        for d in sessions:
            prev_us = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
            move = -0.04 if informative and shock[prev_us] else rng.gauss(0, 0.004)
            price *= 1 + move
            closes.append(price)
        level, us_rows = 100.0, []
        for d in us_days:
            level *= 1 + (-0.05 if shock[d] else rng.gauss(0, 0.004))
            us_rows.append((d, {"EWY": level, "^SOX": level * (1 + rng.gauss(0, 0.001))}))
        return synthetic_rows(sessions, closes), us_rows

    def test_samples_never_use_a_us_session_on_or_after_the_target_day(self):
        rows, us_rows = self.make(True, n=60)
        with tempfile.TemporaryDirectory() as tmp:
            o, meta = read_overnight(*write_overnight(tmp, us_rows, next_session="2099-01-01"))
            aligned = align(load_sessions(), o, meta)
            samples = overnight_eval.build_samples(rows, o, meta)
        self.assertTrue(samples)
        for s in samples:
            self.assertLess(aligned[s.target_date].us_date, s.target_date)
            self.assertGreater(s.target_date, s.date)

    def test_informative_overnight_signal_passes_and_noise_does_not_crash(self):
        for informative in (True, False):
            rows, us_rows = self.make(informative)
            with tempfile.TemporaryDirectory() as tmp:
                o, meta = read_overnight(*write_overnight(tmp, us_rows, next_session="2099-01-01"))
                result = overnight_eval.run(rows, o, meta, reps=100)
            if informative:
                self.assertEqual(result["status"], "candidate")
            else:
                self.assertIn(result["status"], ("not_supported", "insufficient_positives"))

    def test_short_history_is_not_judged(self):
        rows, us_rows = self.make(True, n=300)
        with tempfile.TemporaryDirectory() as tmp:
            o, meta = read_overnight(*write_overnight(tmp, us_rows, next_session="2099-01-01"))
            self.assertEqual(overnight_eval.run(rows, o, meta, reps=10)["status"], "insufficient_design_samples")


class MsiCheckTest(unittest.TestCase):
    def test_rally_offset_and_past_only_drawdown_rank(self):
        sessions = [d for d in load_sessions() if d >= "2016-09-13"][:700]
        closes = [100.0 * (1.0005 ** i) for i in range(len(sessions))]
        for i in range(660, 680):
            closes[i] = closes[i - 1] * 1.01  # rally
        closes[680] = closes[679] * 0.95       # drop after the rally
        for i in range(681, 700):
            closes[i] = closes[680]
        rows = [ScoreRow(d, c, 0.1, 0.0, 1.0, "OOS_WALK_FORWARD") for d, c in zip(sessions, closes)]
        checks = msi_check.daily_checks(rows)
        drop = checks[680]
        self.assertLess(drop.ret_pct, -4.9)
        self.assertGreater(drop.ret21_pct, 0)
        self.assertFalse(drop.official)
        self.assertIsNotNone(drop.drawdown_rank)
        changed = [r if i < 690 else ScoreRow(r.date, r.kospi200_close * 0.5, 0.1, 0.0, 1.0, r.record_type) for i, r in enumerate(rows)]
        self.assertEqual(msi_check.daily_checks(changed)[680], drop)  # later prices never change an earlier rank

    def test_committed_scores_produce_a_verdict(self):
        result = msi_check.run(read_scores(ROOT / "data/input/korea_scores.csv"))
        self.assertIn(result["status"], ("revision_supported", "not_supported"))
        self.assertGreater(len(result["design"]["drops"]), 0)


class PreopenTest(unittest.TestCase):
    def rec(self, **kw):
        base = {"krx_date": "2026-11-11", "recorded_at": "2026-11-11T07:30:00+09:00", "category": "ai_semis",
                "stance": "risk_off", "summary": "밤사이 반도체 급락", "source_urls": "https://news.example/a",
                "source_quality": "news", "classifier": "manual"}
        return {**base, **kw}

    def test_window_is_previous_close_to_eight_thirty(self):
        preopen.parse_row(self.rec())
        preopen.parse_row(self.rec(recorded_at="2026-11-10T15:30:00+09:00"))
        for bad in ("2026-11-11T08:30:00+09:00", "2026-11-10T15:29:00+09:00", "2026-11-11T07:30:00", "2026-11-12T07:00:00+09:00"):
            with self.assertRaises(ValueError):
                preopen.parse_row(self.rec(recorded_at=bad))

    def test_vocabulary_and_classifier_names(self):
        for bad in ({"category": "rumor"}, {"stance": "panic"}, {"classifier": "gpt"},
                    {"source_quality": "unsourced"}, {"source_urls": "http://x.example"}):
            with self.assertRaises(ValueError):
                preopen.parse_row(self.rec(**bad))
        preopen.parse_row(self.rec(classifier="llm:claude-opus-5-5", source_urls="", source_quality="unsourced"))

    def test_committed_log_is_valid_and_not_evaluated_before_the_gate(self):
        log = preopen.read_log()
        rows = read_scores(ROOT / "data/input/korea_scores.csv")
        self.assertTrue(all(not s["ready"] for s in preopen.readiness(log, rows).values()))
        few = [preopen.parse_row(self.rec(krx_date="2026-11-10", recorded_at="2026-11-10T08:00:00+09:00"))]
        self.assertFalse(preopen.readiness(few, rows)["manual"]["ready"])


class ReportTest(unittest.TestCase):
    def test_report_renders_without_overnight_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = signal_checks.render(
                ROOT / "data/input/korea_scores.csv", ROOT / "data/input/provenance.json",
                ROOT / "data/events/kospi_2026_events.csv", Path(tmp) / "missing.csv", Path(tmp) / "missing.json",
                preopen.DEFAULT_LOG, ROOT / "data/events/scheduled_us_2026.csv")
        self.assertIn("데이터 미수집", md)
        self.assertIn("## 2. 공식 MSI", md)
        self.assertIn("| 2026-10-15 | 미국 CPI 2026-10-14 |", md)


if __name__ == "__main__":
    unittest.main()
