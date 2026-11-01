import runpy
import unittest
from pathlib import Path

F = runpy.run_path(str(Path(__file__).with_name('approved_mo_demand_rounding.py')))['demand_quantity']


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.mo = {'id': 1, 'move_raw_ids': [10], 'product_qty': 3, 'qty_producing': 3}
        self.move = {'id': 10, 'product_uom_qty': .62448}
        self.row = dict(source_mo=1, source_id=10, model='stock.move', role='raw',
                        field='product_uom_qty', source_quantity=.62448,
                        target_unit=473, precision=.01, proposed_target_quantity=.62)
        self.approval = {'approved_source_mos': [1], 'approved_rows': [self.row]}

    def test_exact_permission_preserves_header_and_source(self):
        value, record = F(self.mo, self.move, 473, .01, self.approval)
        self.assertEqual(value, .62)
        self.assertEqual(record['source_quantity'], .62448)
        self.assertEqual(self.move['product_uom_qty'], .62448)
        self.assertEqual(self.mo['product_qty'], 3)
        self.assertEqual(self.mo['qty_producing'], 3)

    def test_unapproved_move_unchanged(self):
        self.assertEqual(F(self.mo, dict(self.move, id=11), 473, .01, self.approval), (.62448, None))

    def test_scope_and_drift_rejected(self):
        cases = [(dict(self.mo, id=2), self.move, 473, .01),
                 (dict(self.mo, move_raw_ids=[]), self.move, 473, .01),
                 (self.mo, dict(self.move, product_uom_qty=.625), 473, .01),
                 (self.mo, self.move, 474, .01), (self.mo, self.move, 473, .001)]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(RuntimeError):
                F(*args, self.approval)

    def test_header_or_finished_permission_rejected(self):
        for field, value in [('field', 'qty_producing'), ('role', 'finished_or_byproduct')]:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                F(self.mo, self.move, 473, .01,
                  dict(self.approval, approved_rows=[dict(self.row, **{field: value})]))


if __name__ == '__main__':
    unittest.main()
