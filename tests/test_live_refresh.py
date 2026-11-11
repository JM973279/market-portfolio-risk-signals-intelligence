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
from qsignals.refresh import (RefreshError, archive, check_ecos_key, check_krx_key, check_provider_keys, find_v1_commit,
                              freshness, install_reference, key_fingerprint, load_env, prune_runs, run_logged, us_importable)


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

    def test_refresh_stops_before_any_snapshot_or_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(f"KRX_API_KEY={self.KRX}\nECOS_API_KEY={self.ECOS}\n", encoding="utf-8")
            argv = ["--env-file", str(env_file), "--python", str(Path(tmp) / "missing-python"),
                    "--work-root", str(Path(tmp) / "runs"), "--v1-data", str(Path(tmp) / "v1-data")]
            with patch("qsignals.refresh._http_get", return_value=self.REJECTED) as get, \
                 patch("qsignals.refresh.archive", side_effect=AssertionError("snapshot started")), \
                 patch.dict(os.environ, {"GITHUB_ACTIONS": ""}), self.assertRaises(SystemExit) as stop:
                refresh.main(argv)
            self.assertIn("Provider rejected KRX_API_KEY", str(stop.exception.code))
            self.assertEqual(get.call_count, 2)  # KRX only; ECOS is checked by --check-keys
            self.assertFalse((Path(tmp) / "runs").exists())

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
