"""Image build contexts keep exactly the snapshot current.json points to."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from qsignals.portfolio_data import load_dataset
from scripts import trim_snapshots

ROOT = Path(__file__).resolve().parent.parent


class TrimSnapshotsTest(unittest.TestCase):
    def test_keeps_only_the_current_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp)
            for name in ("old", "current"):
                (dataset / "snapshots" / name / "receipts").mkdir(parents=True)
                (dataset / "snapshots" / name / "prices.csv").write_text("x")
            (dataset / "current.json").write_text(json.dumps({
                "files": {"prices.csv": {"path": "snapshots/current/prices.csv"}},
                "collection": {"receipts": {"r.csv": {"path": "snapshots/current/receipts/r.csv"}}}}))
            self.assertEqual(trim_snapshots.trim(dataset), (["current"], 1))
            self.assertEqual([p.name for p in (dataset / "snapshots").iterdir()], ["current"])

    def test_refuses_when_the_current_snapshot_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp)
            (dataset / "snapshots" / "old").mkdir(parents=True)
            (dataset / "current.json").write_text(json.dumps({"files": {"p.csv": {"path": "snapshots/gone/p.csv"}}}))
            with self.assertRaises(ValueError):
                trim_snapshots.trim(dataset)
            self.assertTrue((dataset / "snapshots" / "old").exists())

    def test_published_datasets_still_load_after_trimming_a_copy(self):
        import shutil
        for name in ("portfolio", "portfolio-kr"):
            with tempfile.TemporaryDirectory() as tmp:
                copy = Path(tmp) / name
                shutil.copytree(ROOT / "data" / name, copy)
                with redirect_stdout(io.StringIO()):
                    trim_snapshots.main([str(copy)])
                self.assertEqual(len(list((copy / "snapshots").iterdir())), 1)
                load_dataset(copy)


if __name__ == "__main__":
    unittest.main()
