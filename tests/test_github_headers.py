"""GitHub API reads carry the Actions token; other hosts never get it."""
import unittest
from unittest.mock import patch

from qsignals.import_scores import _github_headers


class GithubHeadersTest(unittest.TestCase):
    def test_token_goes_only_to_the_github_api(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "t0ken"}, clear=False):
            api = _github_headers("https://api.github.com/repos/o/r/commits/main")
            raw = _github_headers("https://raw.githubusercontent.com/o/r/sha/file.json")
            other = _github_headers("https://api.github.com.evil.example/x")
        self.assertEqual(api["Authorization"], "Bearer t0ken")
        self.assertNotIn("Authorization", raw)
        self.assertNotIn("Authorization", other)

    def test_anonymous_without_a_token(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertNotIn("Authorization", _github_headers("https://api.github.com/repos/o/r/commits/main"))


if __name__ == "__main__":
    unittest.main()
