import copy
import json
import tempfile
import unittest
from pathlib import Path
from qsignals.collection_status import save_collection_status, apply_collection_status
from qsignals.collection_summary import render


class CollectionStatusTest(unittest.TestCase):
    def test_delay_receipt_does_not_rewrite_score_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('korea_scores.csv', 'provenance.json'):
                (root / name).write_text('original publication')
            block = {'status': 'DELAYED', 'expectedDate': '2026-11-27',
                     'lastValid': {'date': '2026-11-26'}, 'reason': 'late credit',
                     'series': [{'name': 'credit', 'status': 'OBSERVED', 'observationDate': '2026-11-26'}]}
            record = save_collection_status({'runId': 'new', 'generatedAt': '2026-11-28T04:06:31+00:00',
                                             'markets': {'korea': block}}, root)
            self.assertEqual(record['markets']['korea']['lateSources'], ['credit'])
            self.assertEqual(json.loads((root / 'collection_status.json').read_text()), record)
            for name in ('korea_scores.csv', 'provenance.json'):
                self.assertEqual((root / name).read_text(), 'original publication')
            saved = {'generatedAt': '2026-11-27T03:00:00+00:00', 'block': {
                'status': 'CURRENT', 'current': {'date': '2026-11-26'},
                'history': [{'date': '2026-11-26', 'risk': .3}], 'lastValid': {'date': '2026-11-26'}}}
            history = copy.deepcopy(saved['block']['history'])
            apply_collection_status(saved, 'korea', record)
            self.assertEqual(saved['block']['status'], 'DELAYED')
            self.assertIsNone(saved['block']['current'])
            self.assertEqual(saved['block']['history'], history)
            self.assertEqual(saved['block']['lastValid']['date'], '2026-11-26')

    def test_stale_receipts_do_not_override_newer_publication(self):
        saved = {'generatedAt': '2026-11-28', 'block': {'status': 'CURRENT'}}
        apply_collection_status(saved, 'us', {'checkedAt': '2026-11-27', 'markets': {'us': {'status': 'DELAYED'}}})
        self.assertEqual(saved['block'], {'status': 'CURRENT'})

    def test_current_receipt_cannot_promote_old_score(self):
        saved = {'generatedAt': '2026-11-27', 'block': {'status': 'DELAYED', 'current': None}}
        apply_collection_status(saved, 'us', {'checkedAt': '2026-11-28', 'markets': {'us': {'status': 'CURRENT'}}})
        self.assertEqual(saved['block']['status'], 'DELAYED')
        self.assertIsNone(saved['block']['current'])

    def test_summary_names_lagging_input(self):
        result = render({'markets': {'us': {'status': 'DELAYED', 'expected_date': '2026-11-25',
                         'last_valid_date': '2026-11-24', 'series': {'DBAA': '2026-11-24', 'DGS10': '2026-11-25'}}}})
        self.assertIn('DBAA: 2026-11-24', result)
        self.assertNotIn('DGS10:', result)
