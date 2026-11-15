"""A late or unreachable provider keeps the published data and retries; a long gap still fails."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from qsignals import import_scores, overnight_refresh, portfolio_korea_refresh, portfolio_refresh, refresh
from qsignals.deferral import MAX_BEHIND, deferral, transient_network_error
from qsignals.portfolio_data import PortfolioError
from tests.test_live_refresh import write_korea

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = ["2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12"]


def captured(fn, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = fn(*args)
    return result, out.getvalue() + err.getvalue()


class PolicyTest(unittest.TestCase):
    def test_provider_problems_within_the_limit_are_deferred(self):
        for code in ("collection_failed", "missing_price", "provider_withheld", "provider_delayed", "stale_data"):
            message = deferral(PortfolioError("late", code), SESSIONS, SESSIONS[-1 - MAX_BEHIND])
            self.assertIn(f"게시본 {SESSIONS[-1 - MAX_BEHIND]} 유지", message, code)

    def test_long_gaps_integrity_and_configuration_errors_and_first_publication_fail(self):
        self.assertIsNone(deferral(PortfolioError("late", "collection_failed"), SESSIONS, SESSIONS[-2 - MAX_BEHIND]))
        for code in ("invalid_data", "config_error", "invalid_input"):
            self.assertIsNone(deferral(PortfolioError("bad", code), SESSIONS, SESSIONS[-1]), code)
        self.assertIsNone(deferral(PortfolioError("late", "collection_failed"), SESSIONS, None))
        self.assertIsNone(deferral(ValueError("bug"), SESSIONS, SESSIONS[-1]))


class NetworkTest(unittest.TestCase):
    def test_only_outages_are_transient(self):
        import urllib.error
        def http(code):
            return urllib.error.HTTPError("https://example.invalid", code, "x", {}, None)
        self.assertTrue(all(map(transient_network_error, [http(500), http(503), http(429),
                                                          urllib.error.URLError("down"), TimeoutError()])))
        self.assertFalse(any(map(transient_network_error, [http(404), http(401), ValueError("bad export")])))

    def test_diagnostics_import_retries_then_keeps_the_published_files(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")) as urlopen, \
             patch.object(import_scores.time, "sleep"), \
             patch.object(import_scores, "load_source", side_effect=lambda *a: import_scores._download("https://x")), \
             patch.object(import_scores, "import_data") as imported:
            _, out = captured(import_scores.main, [])
        self.assertEqual(urlopen.call_count, 3)
        self.assertIn("::warning::", out)
        imported.assert_not_called()
        with patch.object(import_scores, "load_source", side_effect=ValueError("Source export schema changed")), \
             self.assertRaises(ValueError):
            captured(import_scores.main, [])


class RefresherTest(unittest.TestCase):
    def test_korea_portfolio_keeps_snapshot_on_outage_and_fails_when_far_behind(self):
        published = json.loads((ROOT / "data/portfolio-kr/current.json").read_text())["price_as_of"]
        argv = ["x", "--output-dir", str(ROOT / "data/portfolio-kr")]
        outage = PortfolioError("Provider request failed; previous snapshot was preserved.", "collection_failed")
        with patch.object(sys, "argv", argv), \
             patch.object(portfolio_korea_refresh, "refresh", side_effect=outage), \
             patch.object(portfolio_korea_refresh, "completed_sessions", return_value=[published, "2099-01-02"]):
            code, out = captured(portfolio_korea_refresh.main)
        self.assertEqual(code, 0)
        self.assertIn("::warning::", out)
        self.assertIn(published, out)
        far = [published] + [f"2099-01-0{i}" for i in range(1, MAX_BEHIND + 2)]
        with patch.object(sys, "argv", argv), \
             patch.object(portfolio_korea_refresh, "refresh", side_effect=outage), \
             patch.object(portfolio_korea_refresh, "completed_sessions", return_value=far):
            code, out = captured(portfolio_korea_refresh.main)
        self.assertEqual(code, 1)
        self.assertNotIn("::warning::", out)

    def test_korea_rejected_key_is_a_configuration_error(self):
        import urllib.error
        error = urllib.error.HTTPError("https://example.invalid", 401, "Unauthorized", {}, None)
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(PortfolioError) as caught:
            portfolio_korea_refresh.request_json("https://example.invalid")
        self.assertEqual(caught.exception.code, "config_error")

    def test_us_portfolio_defers_within_the_limit_only(self):
        outage = PortfolioError("Yahoo 전체 자산 수집 실패. 기존 검증 자료를 보존합니다.", "collection_failed")
        with patch.object(sys, "argv", ["x"]), patch.object(portfolio_refresh, "refresh", side_effect=outage):
            with patch.object(portfolio_refresh, "_published_position", return_value=(SESSIONS, SESSIONS[-2])):
                _, out = captured(portfolio_refresh.main)
                self.assertIn("::warning::", out)
            with patch.object(portfolio_refresh, "_published_position", return_value=(SESSIONS, SESSIONS[0])), \
                 self.assertRaises(PortfolioError):
                captured(portfolio_refresh.main)

    def test_overnight_keeps_stored_prices_when_yahoo_is_unreachable(self):
        with tempfile.TemporaryDirectory() as tmp:
            provenance = Path(tmp) / "p.json"
            provenance.write_text(json.dumps({"last_date": SESSIONS[-2]}))
            outage = PortfolioError("Yahoo 전체 자산 수집 실패. 기존 검증 자료를 보존합니다.", "collection_failed")
            with patch.object(overnight_refresh, "DEFAULT_PROVENANCE", provenance), \
                 patch.object(overnight_refresh, "completed_sessions", return_value=SESSIONS), \
                 patch.object(overnight_refresh, "fetch_quotes", side_effect=outage), \
                 patch.object(overnight_refresh, "publish") as publish:
                _, out = captured(overnight_refresh.main, [])
                self.assertIn("::warning::", out)
                publish.assert_not_called()
                provenance.write_text(json.dumps({"last_date": SESSIONS[0]}))
                with self.assertRaises(PortfolioError):
                    captured(overnight_refresh.main, [])


class V1RefreshTest(unittest.TestCase):
    def test_unreachable_providers_are_not_a_rejected_key(self):
        down = (None, b"unreachable after 3 attempts (timed out)")
        with patch.object(refresh, "_fetch", return_value=down), self.assertRaises(refresh.ProvidersUnreachable):
            captured(refresh.check_provider_keys, {"KRX_API_KEY": "k"}, False)
        rejected = (401, b'{"respMsg": "Unauthorized Key"}')
        with patch.object(refresh, "_fetch", return_value=rejected), self.assertRaises(SystemExit):
            captured(refresh.check_provider_keys, {"KRX_API_KEY": "k"}, False)

    def test_krx_outage_does_not_stop_the_us_refresh(self):
        # KRX feeds Korea only: an outage keeps Korea late (no alert) and US still runs.
        # The full flow is covered by tests.test_live_refresh.MarketIndependenceTest.
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(refresh, "load_env", return_value={"KRX_API_KEY": "k", "ECOS_API_KEY": "e"}), \
             patch.object(refresh, "check_provider_keys", side_effect=refresh.ProvidersUnreachable("down")), \
             patch.object(refresh, "archive", side_effect=AssertionError("snapshot started")), \
             contextlib.redirect_stderr(err), self.assertRaisesRegex(AssertionError, "snapshot started"):
            # Never the default ~/.cache work root: main prunes older run folders there.
            refresh.main(["--python", sys.executable, "--output-dir", str(ROOT / "data/input"),
                          "--work-root", str(Path(tmp) / "runs"), "--v1-data", str(Path(tmp) / "v1-data")])
        self.assertIn("US is refreshed as usual", err.getvalue())

    def test_lag_marks_a_market_stale_only_past_the_limit(self):
        now = datetime(2026, 11, 13, 1, 0, tzinfo=timezone.utc)  # 10:00 KST Friday
        with tempfile.TemporaryDirectory() as tmp:
            for market, last in (("korea", "2026-11-12"), ("us", "2026-11-05")):
                (Path(tmp) / f"{market}_scores.csv").write_text(f"date,x\n2026-11-02,1\n{last},1\n")
            summary = refresh.with_lag({}, tmp, now)
        self.assertEqual(summary["lag"]["korea"], {"published": "2026-11-12", "expected": "2026-11-12", "behind": 0})
        self.assertEqual(summary["lag"]["us"], {"published": "2026-11-05", "expected": "2026-11-11", "behind": 4})
        self.assertEqual(summary["stale"], ["us"])

    def test_failed_top_up_continues_from_the_cache_but_not_without_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            raw, tree, log = tmp / "data/raw/korea", tmp / "tree", tmp / "log"
            raw.mkdir(parents=True)
            write_korea(raw, "2026-11-11", "2026-11-11", ["2026-11-11,3.6,4.3,0.7,70.0\n"])
            with patch.object(refresh, "run_logged", return_value=1):
                _, out = captured(refresh.top_up_korea_raw, "py", tree, tmp / "data", {}, log)
                self.assertIn("continuing with the cached history", out)
                self.assertTrue((tree / "data/raw/korea/vkospi.csv").exists())
                (raw / "vkospi.csv").unlink()
                with self.assertRaises(refresh.RefreshError):
                    captured(refresh.top_up_korea_raw, "py", tree, tmp / "data", {}, log)

    def test_hung_child_is_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = refresh.run_logged([sys.executable, "-c", "import time; time.sleep(30)"], tmp, {}, Path(tmp) / "log",
                                      timeout=0.5)
            self.assertEqual(code, 124)
            self.assertIn("stopped after", (Path(tmp) / "log").read_text())


if __name__ == "__main__":
    unittest.main()
