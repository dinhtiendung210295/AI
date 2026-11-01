"""Offline checks for SO batch confirmation invariants."""
import copy
import runpy
import unittest
from pathlib import Path

runner = runpy.run_path(str(Path(__file__).with_name('confirm_pysb_july_so_staging.py')))


class BatchVerificationTests(unittest.TestCase):
    def setUp(self):
        before = dict.fromkeys(runner['ORDER'], False)
        before.update(id=1, state='draft', date_order='2026-07-01 00:00:00', picking_ids=[], invoice_ids=[], order_line=[2])
        self.groups = [{'source': {'date_order': '2026-07-01 07:00:00'}, 'before': before,
                        'lines': [{'id': 2, 'price_unit': 10, 'product_uom_qty': 3}]}]
        self.orders = [dict(before, state='sale', date_order='2026-07-01 07:00:00', picking_ids=[4])]
        self.lines = copy.deepcopy(self.groups[0]['lines'])
        parent = self
        class Reader:
            def read(self, model, ids, fields):
                return parent.orders if model == 'sale.order' else parent.lines
        self.reader = Reader()

    def test_confirmation_and_receipt_link_pass(self):
        self.assertEqual(runner['verify_group'](self.reader, self.groups)[0]['state'], 'sale')

    def test_current_date_instead_of_history_stops(self):
        self.orders[0]['date_order'] = '2026-10-12 12:00:00'
        with self.assertRaisesRegex(RuntimeError, 'Historical SO date'):
            runner['verify_group'](self.reader, self.groups)

    def test_selling_price_change_stops(self):
        self.lines[0]['price_unit'] = 11
        with self.assertRaisesRegex(RuntimeError, 'Commercial lines'):
            runner['verify_group'](self.reader, self.groups)

    def test_invoice_created_during_confirm_stops(self):
        self.orders[0]['invoice_ids'] = [3]
        with self.assertRaisesRegex(RuntimeError, 'invoice_ids'):
            runner['verify_group'](self.reader, self.groups)

    def test_shipping_partner_change_stops(self):
        self.orders[0]['partner_shipping_id'] = [7, 'Another address']
        with self.assertRaisesRegex(RuntimeError, 'partner_shipping_id'):
            runner['verify_group'](self.reader, self.groups)


if __name__ == '__main__':
    unittest.main()
