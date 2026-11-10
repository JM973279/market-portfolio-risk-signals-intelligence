import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from qsignals.refresh import RefreshError, archive, find_v1_commit, freshness, load_env, prune_runs


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


class EnvTest(unittest.TestCase):
    def test_parses_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("# c\nKRX_API_KEY=abc\nexport ECOS_API_KEY='x=y'\nBAD\n", encoding="utf-8")
            self.assertEqual(load_env(path), {"KRX_API_KEY": "abc", "ECOS_API_KEY": "x=y"})
            self.assertEqual(load_env(Path(tmp) / "missing"), {})


class FreshnessTest(unittest.TestCase):
    def market(self, **changes):
        m = {"status": "CURRENT", "expectedDate": "2026-11-09", "current": {"date": "2026-11-09"},
             "lastValid": {"date": "2026-11-09"}, "reason": None, "series": [{"name": "KOSPI200", "observationDate": "2026-11-09"}]}
        m.update(changes)
        return m

    def test_current_only_for_expected_session(self):
        self.assertTrue(freshness(self.market())["fresh"])
        self.assertFalse(freshness(self.market(current={"date": "2026-11-06"}))["fresh"])
        self.assertFalse(freshness(self.market(status="DELAYED", current=None))["fresh"])
        blocked = freshness(self.market(status="BLOCKED", current=None, reason="mismatch"))
        self.assertFalse(blocked["fresh"])
        self.assertEqual(blocked["reason"], "mismatch")


if __name__ == "__main__":
    unittest.main()
