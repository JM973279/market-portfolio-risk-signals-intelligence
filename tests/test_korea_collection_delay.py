import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None

from qsignals._collection_worker import adapted_source, complete_korea_history
from qsignals.korea_status import save_delayed_status
from qsignals.scores import ScoreRow, write_scores


CHANNELS = ['KOSPI200', 'VKOSPI', 'Korea_Treasury_3Y', 'Korea_Corporate_AAminus_3Y']


def observations():
    return pd.DataFrame({c: [1., 2., 3.] for c in CHANNELS},
                        index=pd.to_datetime(['2026-11-18', '2026-11-19', '2026-11-20']))


@unittest.skipIf(pd is None, "Requires the existing inference environment (pandas)")
class CollectionBoundaryTest(unittest.TestCase):
    def test_only_late_tail_is_trimmed_and_source_is_preserved(self):
        raw = observations()
        raw.loc['2026-11-20', CHANNELS[-1]] = float('nan')
        before = raw.copy(deep=True)
        result = complete_korea_history(raw, CHANNELS)
        self.assertEqual(result.index[-1].strftime('%Y-%m-%d'), '2026-11-19')
        pd.testing.assert_frame_equal(result, before.iloc[:2])
        pd.testing.assert_frame_equal(raw, before)
        self.assertTrue(result.notna().all().all())

    def test_each_required_source_can_arrive_late(self):
        for channel in CHANNELS[1:]:
            with self.subTest(channel=channel):
                raw = observations()
                raw.loc['2026-11-20', channel] = float('nan')
                self.assertEqual(len(complete_korea_history(raw, CHANNELS)), 2)

    def test_catch_up_keeps_the_new_session_and_all_values(self):
        raw = observations()
        pd.testing.assert_frame_equal(complete_korea_history(raw, CHANNELS), raw)

    def test_internal_gap_is_blocked_even_beyond_another_channels_cutoff(self):
        raw = observations()
        raw.loc['2026-11-19', 'VKOSPI'] = float('nan')
        raw.loc['2026-11-19':, CHANNELS[-1]] = float('nan')
        with self.assertRaisesRegex(ValueError, 'no imputation'):
            complete_korea_history(raw, CHANNELS)

    def test_missing_entire_channel_is_blocked(self):
        raw = observations()
        raw[CHANNELS[-1]] = float('nan')
        with self.assertRaisesRegex(ValueError, 'no imputation'):
            complete_korea_history(raw, CHANNELS)

    def test_unrecognized_runner_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            adapted_source('print("different upstream")')

    def test_actual_worker_retains_original_gate_and_due_date(self):
        # Exercise the CLI used by refresh, including its original __file__/argv.
        source = '''import sys
from pathlib import Path
import pandas as pd
assert Path(__file__).name == 'run.py'
assert sys.argv[1:] == ['--collect']
def main():
    due = '2026-11-20'
    raw = pd.DataFrame({'KOSPI200': [799., 755.], 'credit': [4., None]}, index=['2026-11-19', due])
    channels = ['KOSPI200', 'credit']
    if True:
        if True:
            if True:
                equity = raw.loc[raw.KOSPI200.notna()]
                if equity[channels].isna().any().any():
                    raise ValueError('Missing Korea equity-date channel; no imputation')
    last = equity.index[-1]
    print('CURRENT' if last == due else 'DELAYED', last, due)
if __name__ == '__main__':
    main()
'''
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / 'run.py'
            runner.write_text(source)
            worker = Path(__file__).resolve().parents[1] / 'qsignals/_collection_worker.py'
            run = subprocess.run([sys.executable, str(worker), str(runner), '--collect'],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.strip(), 'DELAYED 2026-11-19 2026-11-20')
            self.assertEqual(runner.read_text(), source)


class DelayedStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'operational').mkdir()
        self.path = self.root / 'operational/korea.json'
        self.point = {'date': '2026-11-19', 'risk': .3, 'msi': .2, 'threshold': 1.,
                      'price': None, 'recordType': 'OPERATIONAL'}
        self.saved = {'runId': 'verified-score-run', 'generatedAt': 'old', 'block': {
            'status': 'CURRENT', 'current': self.point, 'lastValid': self.point,
            'expectedDate': '2026-11-19', 'history': [self.point]}}
        self.path.write_text(json.dumps(self.saved))
        write_scores([ScoreRow('2026-11-19', 799.57, .3, .2, 1., 'OPERATIONAL')], self.root / 'korea_scores.csv')
        (self.root / 'provenance.json').write_text('original score provenance')
        self.operational = {'runId': 'new-collection', 'generatedAt': 'new', 'markets': {'korea': {
            'status': 'DELAYED', 'expectedDate': '2026-11-20', 'current': None,
            'lastValid': self.point, 'history': [self.point], 'historicalParity': True,
            'inferenceSucceeded': True, 'reason': 'latest observation pending',
            'series': [{'name': 'Korea_Corporate_AAminus_3Y', 'observationDate': '2026-11-19'}]}}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_pending_status_keeps_scores_dates_and_provenance(self):
        scores = (self.root / 'korea_scores.csv').read_bytes()
        self.assertTrue(save_delayed_status(self.operational, self.root))
        saved = json.loads(self.path.read_text())
        block = saved['block']
        self.assertEqual(block['status'], 'DELAYED')
        self.assertIsNone(block['current'])
        self.assertEqual(block['lastValid'], self.point)
        self.assertEqual(block['expectedDate'], '2026-11-20')
        self.assertEqual(block['series'], self.operational['markets']['korea']['series'])
        self.assertEqual(saved['scoreRunId'], 'verified-score-run')
        self.assertEqual(saved['runId'], 'new-collection')
        self.assertEqual((self.root / 'korea_scores.csv').read_bytes(), scores)
        self.assertEqual((self.root / 'provenance.json').read_text(), 'original score provenance')
        self.assertTrue(save_delayed_status(self.operational, self.root))
        self.assertEqual(json.loads(self.path.read_text())['scoreRunId'], 'verified-score-run')

    def test_changed_score_and_missing_history_are_blocked_before_write(self):
        before = self.path.read_bytes()
        for history in ([], [{**self.point, 'risk': .4}]):
            candidate = copy.deepcopy(self.operational)
            candidate['markets']['korea']['history'] = history
            with self.assertRaisesRegex(ValueError, 'differs'):
                save_delayed_status(candidate, self.root)
            self.assertEqual(self.path.read_bytes(), before)

    def test_blocked_unverified_and_current_results_cannot_be_relabelled(self):
        for changes in ({'status': 'BLOCKED'}, {'status': 'CURRENT'},
                        {'historicalParity': False}, {'inferenceSucceeded': False}):
            candidate = copy.deepcopy(self.operational)
            candidate['markets']['korea'].update(changes)
            self.assertFalse(save_delayed_status(candidate, self.root))

    def test_older_expectation_does_not_replace_newer_status(self):
        self.saved['block']['expectedDate'] = '2026-11-23'
        self.path.write_text(json.dumps(self.saved))
        self.assertFalse(save_delayed_status(self.operational, self.root))
