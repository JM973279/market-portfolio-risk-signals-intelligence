import unittest

from qsignals.export_frontend import check_block
from qsignals.scores import ScoreRow


def rows():
    return [ScoreRow("2026-09-16", 100.0, 0.2, 0.1, 1.0, "OOS_WALK_FORWARD"),
            ScoreRow("2026-11-09", None, 0.47, 1.06, 1.11, "RETROSPECTIVE_INFERENCE")]


def block(**point):
    base = {"date": "2026-11-09", "price": None, "risk": 0.47, "msi": 1.06, "threshold": 1.11}
    return {"history": [{**base, **point}]}


class CheckBlockTest(unittest.TestCase):
    def test_matching_block_passes(self):
        check_block("korea", block(), rows())

    def test_value_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            check_block("korea", block(risk=0.48), rows())

    def test_date_outside_csv_fails(self):
        with self.assertRaisesRegex(ValueError, "not in"):
            check_block("korea", {"history": block()["history"] + [{"date": "2026-11-10", "risk": 0.5}]}, rows())

    def test_csv_row_missing_from_block_fails(self):
        with self.assertRaisesRegex(ValueError, "missing from the status block"):
            check_block("korea", {"history": []}, rows())


if __name__ == "__main__":
    unittest.main()
