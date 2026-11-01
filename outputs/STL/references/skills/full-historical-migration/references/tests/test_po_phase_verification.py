import runpy
from pathlib import Path
import unittest

summarize = runpy.run_path(str(Path(__file__).parents[1] / 'verify_pysb_phase_orders.py'))['summarize']


class GateTests(unittest.TestCase):
    def test_eligible_order_prevents_phase_closure(self):
        gate = summarize([dict(source_id=1, status='eligible_unattempted')], [1])
        self.assertEqual('in_progress', gate['status'])
        self.assertEqual(1, gate['eligible_unattempted'])

    def test_holds_remain_explicit(self):
        rows = [dict(source_id=1, status='verified_confirmed'), dict(source_id=2, status='held', reasons=[{'reason': 'missing_target_order'}])]
        gate = summarize(rows, [1, 2])
        self.assertEqual('closed_with_holds', gate['status'])
        self.assertEqual(1, gate['held_count'])

    def test_missing_or_duplicate_or_unclassified_order_rejected(self):
        cases = [[], [dict(source_id=1, status='verified_confirmed')] * 2, [dict(source_id=1, status='unknown')], [dict(source_id=1, status='held', reasons=[])]]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                summarize(rows, [1])
