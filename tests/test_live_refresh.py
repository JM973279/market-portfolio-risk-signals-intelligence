import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import os
import urllib.error
from unittest.mock import patch

from qsignals import refresh
from qsignals.refresh import (RefreshError, align_korea_fallback, archive, check_ecos_key, check_krx_key,
                              check_provider_keys, extend_ecos_cache, find_v1_commit, freshness, install_reference,
                              key_fingerprint, load_env, prune_runs, run_logged, us_importable)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class V1CommitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "v1"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "test@example.org")
        git(self.repo, "config", "user.name", "test")
        git(self.repo, "config", "core.autocrlf", "false")

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, files, message):
        for rel, text in files.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)
        return subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def test_finds_matching_commit_on_another_branch(self):
        good = self.commit({"src/a.py": "a1\n", "src/b.py": "b1\n"}, "contract version")
        git(self.repo, "switch", "-q", "-c", "feature")
        self.commit({"src/a.py": "a2\n"}, "later change on the checked-out branch")
        found = find_v1_commit(self.repo, {"src/a.py": sha("a1\n"), "src/b.py": sha("b1\n")})
        self.assertEqual(found, good)

    def test_rejects_partial_match(self):
        self.commit({"src/a.py": "a1\n", "src/b.py": "b1\n"}, "c")
        with self.assertRaises(RefreshError):
            find_v1_commit(self.repo, {"src/a.py": sha("a1\n"), "src/b.py": sha("other\n")})

    def test_archive_leaves_worktree_alone(self):
        rev = self.commit({"src/a.py": "a1\n"}, "c")
        (self.repo / "src/a.py").write_text("local edit\n", encoding="utf-8")
        dest = Path(self.tmp.name) / "snap"
        self.assertEqual(archive(self.repo, rev, dest), rev)
        self.assertEqual((dest / "src/a.py").read_text(encoding="utf-8"), "a1\n")
        self.assertEqual((self.repo / "src/a.py").read_text(encoding="utf-8"), "local edit\n")


ECOS_HEAD = "\ufeffDate,Korea_Treasury_3Y,Korea_Corporate_AAminus_3Y,Korea_Credit_Spread,Korea_Credit_Spread_bp\n"


def write_korea(folder, krx_last, vkospi_last, ecos_rows):
    folder = Path(folder)
    days = ["2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11"]
    (folder / "krx_indices.csv").write_text("Date,Index,Close\n" + "".join(
        f"{d},{i},1.0\n" for d in days if d <= krx_last for i in ("KOSPI", "KOSPI200")), encoding="utf-8")
    (folder / "vkospi.csv").write_text("Date,Index,Close\n" + "".join(
        f"{d},VKOSPI,20.0\n" for d in days if d <= vkospi_last), encoding="utf-8")
    (folder / "ecos_credit.csv").write_text(ECOS_HEAD + "".join(ecos_rows), encoding="utf-8")


class KoreaFallbackTest(unittest.TestCase):
    def test_snapshot_copies_end_on_the_last_date_every_channel_has(self):
        # 11-13 05:43 KST: KRX through 11-11, ECOS cache only through 11-09 -> run.py blocked Korea.
        with tempfile.TemporaryDirectory() as tmp:
            write_korea(tmp, "2026-11-11", "2026-11-11", ["2026-11-06,3.6,4.3,0.7,70.0\n", "2026-11-09,3.6,4.3,0.7,70.0\n",
                                                          "2026-11-10,3.6,,,\n"])
            ecos = (Path(tmp) / "ecos_credit.csv").read_bytes()
            self.assertEqual(align_korea_fallback(tmp), "2026-11-09")
            for name in ("krx_indices.csv", "vkospi.csv"):
                last = (Path(tmp) / name).read_text().splitlines()[-1]
                self.assertTrue(last.startswith("2026-11-09,"), name)
            self.assertEqual((Path(tmp) / "ecos_credit.csv").read_bytes(), ecos[:ecos.index(b"2026-11-10")])
            self.assertEqual(align_korea_fallback(tmp), "2026-11-09")  # idempotent

    def test_aligned_history_is_left_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_korea(tmp, "2026-11-11", "2026-11-11", [f"{d},3.6,4.3,0.7,70.0\n" for d in
                                                          ("2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11")])
            before = {p.name: p.read_bytes() for p in Path(tmp).iterdir()}
            self.assertEqual(align_korea_fallback(tmp), "2026-11-11")
            self.assertEqual({p.name: p.read_bytes() for p in Path(tmp).iterdir()}, before)


class EcosCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache, self.collected = Path(self.tmp.name) / "cache.csv", Path(self.tmp.name) / "run.csv"
        self.cache.write_text(ECOS_HEAD + "2026-11-06,3.6,4.3,0.7,70.0\n2026-11-09,3.7,4.4,0.7,70.0\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, rows):
        self.collected.write_text(ECOS_HEAD.lstrip("\ufeff") + "".join(rows), encoding="utf-8")

    def test_appends_only_new_verified_rows_and_keeps_the_original_bytes(self):
        before = self.cache.read_bytes()
        self.collect(["2026-11-06,3.6,4.3,0.7,70.0\n", "2026-11-09,3.7,4.4,0.7,70.0\n", "2026-11-10,3.8,4.5,0.7,70.0\n"])
        self.assertEqual(extend_ecos_cache(self.collected, self.cache), 1)
        self.assertEqual(self.cache.read_bytes(), before + b"2026-11-10,3.8,4.5,0.7,70.0\n")
        self.assertEqual(extend_ecos_cache(self.collected, self.cache), 0)

    def test_revised_or_missing_history_and_absent_files_change_nothing(self):
        before = self.cache.read_bytes()
        for rows in (["2026-11-06,3.6,4.3,0.7,70.0\n", "2026-11-09,3.9,4.4,0.5,50.0\n", "2026-11-10,3.8,4.5,0.7,70.0\n"],
                     ["2026-11-09,3.7,4.4,0.7,70.0\n", "2026-11-10,3.8,4.5,0.7,70.0\n"]):
            self.collect(rows)
            self.assertEqual(extend_ecos_cache(self.collected, self.cache), 0)
        self.assertEqual(extend_ecos_cache(Path(self.tmp.name) / "none.csv", self.cache), 0)
        self.assertEqual(self.cache.read_bytes(), before)


class PruneTest(unittest.TestCase):
    def test_keeps_newest_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ["20261101T000000Z", "20261102T000000Z", "20261103T000000Z", "notes"]:
                (Path(tmp) / name).mkdir()
            prune_runs(tmp, 2)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["20261102T000000Z", "20261103T000000Z", "notes"])


class ReferenceInstallTest(unittest.TestCase):
    REF = "data/processed/early_warning_v2/korea_feature_matrix_v1_reproduction.csv"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.work, self.refdir = root / "work", root / "reference"
        (self.work / "mpri/market_engine/operations").mkdir(parents=True)
        self.refdir.mkdir()
        self.contract = {"markets": {"korea": {"reference": self.REF, "reference_sha256": "orig"}}}
        (self.refdir / "korea_feature_matrix_v1_reproduction.csv").write_bytes(b"rebuilt\n")

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self, **changes):
        report = {"passed": True, "contract_reference_sha256": "orig", "rebuilt_sha256": sha("rebuilt\n"), "end": "2026-10-02", "checks": {}}
        report.update(changes)
        (self.refdir / "verification.json").write_text(json.dumps(report), encoding="utf-8")

    def test_original_wins(self):
        target = self.work / "mpri" / self.REF
        target.parent.mkdir(parents=True)
        target.write_text("original\n", encoding="utf-8")
        self.assertIsNone(install_reference(self.work, self.contract, self.refdir))
        self.assertEqual(target.read_text(encoding="utf-8"), "original\n")

    def test_installs_verified_rebuild_into_snapshot_only(self):
        self.verify()
        info = install_reference(self.work, self.contract, self.refdir)
        self.assertTrue(info["rebuilt"])
        self.assertEqual((self.work / "mpri" / self.REF).read_text(encoding="utf-8"), "rebuilt\n")
        written = json.loads((self.work / "mpri/market_engine/operations/contract.json").read_text(encoding="utf-8"))
        self.assertEqual(written["markets"]["korea"]["reference_sha256"], sha("rebuilt\n"))

    def test_rejections(self):
        for changes in ({"passed": False}, {"contract_reference_sha256": "other"}, {"rebuilt_sha256": "tampered"}):
            self.verify(**changes)
            with self.assertRaises(RefreshError):
                install_reference(self.work, json.loads(json.dumps(self.contract)), self.refdir)
        (self.refdir / "verification.json").unlink()
        with self.assertRaises(RefreshError):
            install_reference(self.work, self.contract, self.refdir)


class EnvTest(unittest.TestCase):
    def test_parses_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("# c\nKRX_API_KEY=abc\nexport ECOS_API_KEY='x=y'\nBAD\n", encoding="utf-8")
            self.assertEqual(load_env(path), {"KRX_API_KEY": "abc", "ECOS_API_KEY": "x=y"})
            self.assertEqual(load_env(Path(tmp) / "missing"), {})


class KeyCheckTest(unittest.TestCase):
    KRX = "k" * 40
    ECOS = "e" * 20
    REJECTED = (401, b'{"respMsg":"Unauthorized Key","respCode":"401"}')

    def setUp(self):
        # Keep check output (incl. a "::error" line) out of the CI log, where it would become an annotation.
        stderr = patch("sys.stderr", new_callable=io.StringIO)
        self.stderr = stderr.start()
        self.addCleanup(stderr.stop)

    def test_accepted_key_checks_both_downloader_endpoints(self):
        with patch("qsignals.refresh._http_get", return_value=(200, b'{"OutBlock_1": []}')) as get:
            self.assertEqual(check_krx_key(self.KRX), [])
        urls = [call.args[0] for call in get.call_args_list]
        self.assertEqual([u.split("?")[0].rsplit("/", 1)[-1] for u in urls], ["kospi_dd_trd", "drvprod_dd_trd"])
        self.assertTrue(all(call.args[1] == {"AUTH_KEY": self.KRX} for call in get.call_args_list))

    def test_rejected_key_stops_with_fingerprint_not_value(self):
        with patch("qsignals.refresh._http_get", return_value=self.REJECTED), \
             patch.dict(os.environ, {"GITHUB_ACTIONS": "", "GITHUB_STEP_SUMMARY": ""}):
            problems = check_krx_key(self.KRX)
            with self.assertRaises(SystemExit) as stop:
                check_provider_keys({"KRX_API_KEY": self.KRX, "ECOS_API_KEY": self.ECOS}, ecos=False)
        self.assertEqual(len(problems), 2)
        self.assertIn("HTTP 401 Unauthorized Key", problems[0])
        message = str(stop.exception.code)
        self.assertIn("Provider rejected KRX_API_KEY", message)
        self.assertIn(key_fingerprint(self.KRX), message)
        self.assertNotIn(self.KRX, message)
        self.assertIn("Update the value", message)

    def test_known_key_without_service_approval_does_not_blame_the_secret(self):
        refused = (401, b'{"respMsg":"Unauthorized API Call","respCode":"401"}')
        with patch("qsignals.refresh._http_get", return_value=refused), \
             patch.dict(os.environ, {"GITHUB_ACTIONS": "", "GITHUB_STEP_SUMMARY": ""}), \
             self.assertRaises(SystemExit) as stop:
            check_provider_keys({"KRX_API_KEY": self.KRX, "ECOS_API_KEY": self.ECOS}, ecos=False)
        message = str(stop.exception.code)
        self.assertIn("replacing the secret will not help", message)
        self.assertNotIn("Update the value", message)

    def test_step_summary_on_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            with patch("qsignals.refresh._http_get", return_value=self.REJECTED), \
                 patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": str(summary)}), \
                 self.assertRaises(SystemExit):
                check_provider_keys({"KRX_API_KEY": self.KRX, "ECOS_API_KEY": self.ECOS}, ecos=False)
            text = summary.read_text(encoding="utf-8")
        self.assertIn("API key rejected", text)
        self.assertNotIn(self.KRX, text)
        self.assertIn("::error title=API key rejected::", self.stderr.getvalue())
        self.assertNotIn(self.KRX, self.stderr.getvalue())

    def test_unreachable_provider_is_reported_without_url(self):
        with patch("qsignals.refresh._http_get", side_effect=urllib.error.URLError("timed out")), \
             patch("qsignals.refresh.time.sleep") as sleep:
            ecos = check_ecos_key(self.ECOS)
        self.assertEqual(sleep.call_count, 2)
        self.assertIn("unreachable after 3 attempts (timed out)", ecos[0])
        self.assertNotIn(self.ECOS, ecos[0])

    def test_ecos_result_error(self):
        body = '{"RESULT":{"CODE":"INFO-100","MESSAGE":"인증키가 유효하지 않습니다."}}'.encode()
        with patch("qsignals.refresh._http_get", return_value=(200, body)):
            self.assertEqual(check_ecos_key(self.ECOS), ["StatisticSearch: INFO-100 인증키가 유효하지 않습니다."])
        with patch("qsignals.refresh._http_get", return_value=(200, b'{"StatisticSearch": {"row": []}}')):
            self.assertEqual(check_ecos_key(self.ECOS), [])

    def test_refused_krx_key_does_not_stop_the_us_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(f"KRX_API_KEY={self.KRX}\nECOS_API_KEY={self.ECOS}\n", encoding="utf-8")
            argv = ["--env-file", str(env_file), "--python", str(Path(tmp) / "missing-python"),
                    "--work-root", str(Path(tmp) / "runs"), "--v1-data", str(Path(tmp) / "v1-data")]
            with patch("qsignals.refresh._http_get", return_value=self.REJECTED) as get, \
                 patch.dict(os.environ, {"GITHUB_ACTIONS": ""}), self.assertRaises(SystemExit) as stop:
                refresh.main(argv)
            # It got past the key check (KRX feeds Korea only) and stopped on the next requirement.
            self.assertIn("Inference Python not found", str(stop.exception.code))
            self.assertEqual(get.call_count, 2)  # KRX only; ECOS is checked by --check-keys
            self.assertIn("US is refreshed as usual", self.stderr.getvalue())

    def test_check_keys_mode_still_stops_on_a_refused_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(f"KRX_API_KEY={self.KRX}\nECOS_API_KEY={self.ECOS}\n", encoding="utf-8")
            responses = [self.REJECTED, self.REJECTED, (200, b'{"StatisticSearch": {}}')]
            with patch("qsignals.refresh._http_get", side_effect=responses), \
                 patch.dict(os.environ, {"GITHUB_ACTIONS": ""}), self.assertRaises(SystemExit) as stop:
                refresh.main(["--check-keys", "--env-file", str(env_file)])
            self.assertIn("Provider rejected KRX_API_KEY", str(stop.exception.code))
            self.assertIn("Nothing was collected or published", str(stop.exception.code))

    def test_refused_krx_key_skips_the_downloaders_but_installs_the_cached_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            v1_data, v1_tree = Path(tmp) / "data", Path(tmp) / "v1"
            raw = v1_data / "raw" / "korea"
            raw.mkdir(parents=True)
            for name in refresh.KOREA_RAW:
                (raw / name).write_text("Date\n", encoding="utf-8")
            with patch("qsignals.refresh.run_logged", side_effect=AssertionError("downloader started")), \
                 patch("qsignals.refresh.align_korea_fallback", return_value="2026-11-12"):
                refresh.top_up_korea_raw(Path("python"), v1_tree, v1_data, {}, Path(tmp) / "log", download=False)
            self.assertTrue(all((v1_tree / "data/raw/korea" / name).exists() for name in refresh.KOREA_RAW))

    def test_check_keys_mode_checks_both_and_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(f"KRX_API_KEY={self.KRX}\nECOS_API_KEY={self.ECOS}\n", encoding="utf-8")
            responses = [(200, b'{"OutBlock_1": []}'), (200, b'{"OutBlock_1": []}'), (200, b'{"StatisticSearch": {}}')]
            with patch("qsignals.refresh._http_get", side_effect=responses), \
                 patch("qsignals.refresh.archive", side_effect=AssertionError("snapshot started")):
                self.assertEqual(refresh.main(["--check-keys", "--env-file", str(env_file)]), 0)

    def test_children_run_unbuffered(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "refresh.log"
            code = run_logged([sys.executable, "-c", "import os; print(os.environ.get('PYTHONUNBUFFERED'))"],
                              tmp, {"PATH": os.environ.get("PATH", "")}, log)
            self.assertEqual(code, 0)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines()[-1], "1")


class MarketIndependenceTest(unittest.TestCase):
    """A Korea failure must never stop US publication (and the run still fails afterwards)."""

    def run_main(self, tmp, korea_status, prepare=None, keys="KRX_API_KEY=k\nECOS_API_KEY=e\n",
                 check=None, import_korea=None):
        tmp = Path(tmp)
        python = tmp / "python"
        python.write_text("", encoding="utf-8")
        env_file = tmp / ".env"
        env_file.write_text(keys, encoding="utf-8")
        current = {"date": "2026-11-13"} if korea_status == "CURRENT" else None
        markets = {
            "korea": {"status": korea_status, "expectedDate": "2026-11-13", "current": current,
                      "lastValid": current, "reason": "x", "series": []},
            "us": {"status": "DELAYED", "expectedDate": "2026-11-13", "current": None, "historicalParity": True,
                   "lastValid": {"date": "2026-11-12"}, "history": [{"date": "2026-11-12"}], "series": []},
        }

        def fake_archive(repo, ref, dest):
            (dest / "market_engine/operations").mkdir(parents=True)
            (dest / refresh.CONTRACT).write_text(json.dumps({"original_sources": {}, "markets": {"korea": {"reference": "ref.csv"}}}))
            return "c" * 40

        def fake_run(cmd, cwd, env, log, timeout=None):
            data = Path(cwd) / "frontend/public/data"
            data.mkdir(parents=True, exist_ok=True)
            (data / "operational-markets.json").write_text(json.dumps({"runId": "r", "markets": markets}))
            (data / "global-markets.json").write_text("{}")
            return 0

        imported, self.downloads = [], []
        prepare = prepare or (lambda *a, download=True: self.downloads.append(download))
        argv = ["--env-file", str(env_file), "--python", str(python), "--work-root", str(tmp / "runs"),
                "--v1-data", str(tmp / "v1-data"), "--output-dir", str(tmp / "out"),
                "--source-root", str(tmp), "--v1-repo", str(tmp)]
        with patch.dict(os.environ, {"KRX_API_KEY": "", "ECOS_API_KEY": ""}), \
             patch("qsignals.refresh.check_provider_keys", side_effect=check), \
             patch("qsignals.refresh.archive", side_effect=fake_archive), \
             patch("qsignals.refresh.find_v1_commit", return_value="v" * 40), \
             patch("qsignals.refresh.top_up_korea_raw", side_effect=prepare), \
             patch("qsignals.refresh.install_reference", return_value=None), \
             patch("qsignals.refresh.run_logged", side_effect=fake_run), \
             patch("qsignals.refresh.extend_ecos_cache", return_value=0), \
             patch("qsignals.refresh.git", side_effect=refresh.RefreshError("no repo")), \
             patch("qsignals.refresh.import_us", side_effect=lambda *a, **k: imported.append("us") or {"last_risk_date": "2026-11-12"}), \
             patch("qsignals.refresh.import_data", side_effect=import_korea or AssertionError("korea imported")), \
             patch("qsignals.refresh.score_lag", return_value={}), \
             patch("sys.stdout", new_callable=io.StringIO) as out, patch("sys.stderr", new_callable=io.StringIO):
            code = refresh.main(argv)
        return code, json.loads(out.getvalue()), imported

    def test_blocked_korea_still_publishes_us_and_raises_an_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, summary, imported = self.run_main(tmp, "BLOCKED")
        self.assertEqual((code, imported, summary["blocked"]), (3, ["us"], ["korea"]))
        self.assertIn("BLOCKED: korea", summary["alerts"][0])

    def test_failed_korea_preparation_still_publishes_us(self):
        def broken(*args, **kwargs):
            raise refresh.RefreshError("V1 downloader download_vkospi failed (exit 1)")
        with tempfile.TemporaryDirectory() as tmp:
            code, summary, imported = self.run_main(tmp, "BLOCKED", prepare=broken)
        self.assertEqual((code, imported), (3, ["us"]))
        self.assertIn("Korea preparation failed", summary["alerts"][0])

    def test_failed_korea_import_still_publishes_us(self):
        def broken(*args, **kwargs):
            raise ValueError("KOSPI200 price check failed")
        with tempfile.TemporaryDirectory() as tmp:
            code, summary, imported = self.run_main(tmp, "CURRENT", import_korea=broken)
        self.assertEqual((code, imported), (0, ["us"]))
        self.assertIn("korea import failed", summary["alerts"][0])

    def test_missing_korea_keys_still_refresh_us(self):
        no_check = AssertionError("keys checked without a value")
        with tempfile.TemporaryDirectory() as tmp:
            code, summary, imported = self.run_main(tmp, "DELAYED", keys="ECOS_API_KEY=e\n", check=no_check)
        self.assertEqual((code, imported, self.downloads), (3, ["us"], [False]))
        self.assertIn("KRX_API_KEY is not set", summary["alerts"][0])

    def test_unreachable_krx_keeps_korea_late_without_an_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, summary, imported = self.run_main(
                tmp, "DELAYED", check=refresh.ProvidersUnreachable("kospi_dd_trd: no response"))
        self.assertEqual((code, imported, summary["alerts"], self.downloads), (3, ["us"], [], [False]))

    def test_delayed_korea_is_not_an_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, summary, imported = self.run_main(tmp, "DELAYED")
        self.assertEqual((code, imported, summary["alerts"], summary["delayed"]), (3, ["us"], [], ["korea"]))


class FreshnessTest(unittest.TestCase):
    def market(self, **changes):
        m = {"status": "CURRENT", "expectedDate": "2026-11-09", "current": {"date": "2026-11-09"},
             "lastValid": {"date": "2026-11-09"}, "reason": None, "series": [{"name": "KOSPI200", "observationDate": "2026-11-09"}]}
        m.update(changes)
        return m

    def test_us_import_gate(self):
        history = [{"date": "2026-11-06", "risk": 0.9}]
        self.assertTrue(us_importable({"status": "DELAYED", "historicalParity": True, "history": history}))
        self.assertTrue(us_importable({"status": "CURRENT", "historicalParity": True, "history": history}))
        self.assertFalse(us_importable({"status": "BLOCKED", "historicalParity": False, "history": history}))
        self.assertFalse(us_importable({"status": "DELAYED", "historicalParity": True, "history": []}))
        self.assertFalse(us_importable({"status": "DELAYED", "history": history}))

    def test_current_only_for_expected_session(self):
        self.assertTrue(freshness(self.market())["fresh"])
        self.assertFalse(freshness(self.market(current={"date": "2026-11-06"}))["fresh"])
        self.assertFalse(freshness(self.market(status="DELAYED", current=None))["fresh"])
        blocked = freshness(self.market(status="BLOCKED", current=None, reason="mismatch"))
        self.assertFalse(blocked["fresh"])
        self.assertEqual(blocked["reason"], "mismatch")


if __name__ == "__main__":
    unittest.main()
