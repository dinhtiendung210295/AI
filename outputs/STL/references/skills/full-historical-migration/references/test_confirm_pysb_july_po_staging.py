"""Offline safety regression tests; never connects to Odoo."""
import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('confirm_po', Path(__file__).with_name('confirm_pysb_july_po_staging.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class FakeReader:
    def __init__(self, order, lines):
        self.order, self.lines = order, lines

    def read(self, model, ids, fields):
        if model == 'uom.uom':
            return [{'id': i, 'factor': 1000 if i != 5 else 1, 'relative_uom_id': [5, 'g'], 'rounding': 0.01} for i in ids]
        return [self.order] if model == 'purchase.order' else self.lines


class ConfirmationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.before = dict.fromkeys(runner.ORDER, False)
        self.before.update(id=1, state='draft', order_line=[10], picking_ids=[], invoice_ids=[],
                           picking_type_id=[2, 'Receipts'], company_id=[1, 'PYSB'])
        self.line = {'id': 10, 'product_id': [20, 'Goods'], 'product_uom_id': [3, 'Units'], 'product_qty': 4}
        self.group = {'before': self.before, 'source': {'date_approve': '2026-07-02 01:00:00'},
                      'lines': [self.line], 'has_stock_goods': True}
        self.after = copy.deepcopy(self.before)
        self.after.update(state='purchase', date_approve=self.group['source']['date_approve'], picking_ids=[30])
        self.workflow = {'pickings': [{'id': 30, 'state': 'assigned', 'date_done': False,
                                       'company_id': [1, 'PYSB'], 'picking_type_id': [2, 'Receipts'],
                                       'location_id': [40, 'Vendor']}],
                         'moves': [{'id': 50, 'state': 'assigned', 'purchase_line_id': [10, 'Line'],
                                    'product_id': [20, 'Goods'], 'product_uom': [3, 'Units'],
                                    'product_uom_qty': 4, 'picking_id': [30, 'Receipt'], 'location_id': [40, 'Vendor']}]}

    def verify(self, lines=None):
        reader = FakeReader(self.after, lines or [self.line])
        with patch.object(runner, 'workflow_snapshot', return_value=self.workflow):
            return runner.verify_order(reader, self.group, {20: {'type': 'consu', 'uom_id': [4, 'kg']}})

    def test_valid_confirm_and_reserved_stock_pass(self):
        self.assertEqual(self.verify()['order']['state'], 'purchase')

    def test_wrong_historical_date_stops(self):
        self.after['date_approve'] = '2026-10-12 01:00:00'
        with self.assertRaisesRegex(RuntimeError, 'Historical date'):
            self.verify()

    def test_new_bill_stops(self):
        self.after['invoice_ids'] = [99]
        with self.assertRaisesRegex(RuntimeError, 'invoice_ids'):
            self.verify()

    def test_changed_commercial_line_stops(self):
        changed = dict(self.line, product_qty=8)
        with self.assertRaisesRegex(RuntimeError, 'Commercial line'):
            self.verify([changed])

    def test_duplicate_move_stops_even_if_total_quantity_matches(self):
        self.workflow['moves'][0]['product_uom_qty'] = 2
        self.workflow['moves'].append(dict(self.workflow['moves'][0], id=51))
        with self.assertRaisesRegex(RuntimeError, 'Multiple direct'):
            self.verify()

    def test_missing_stock_move_stops(self):
        self.workflow['moves'] = []
        with self.assertRaisesRegex(RuntimeError, 'Missing stock move'):
            self.verify()

    def test_done_receipt_stops(self):
        self.workflow['pickings'][0]['state'] = 'done'
        with self.assertRaisesRegex(RuntimeError, 'Receipt unexpectedly completed'):
            self.verify()

    def test_wrong_receipt_company_stops(self):
        self.workflow['pickings'][0]['company_id'] = [2, 'Other']
        with self.assertRaisesRegex(RuntimeError, 'company/type'):
            self.verify()

    def test_equivalent_purchase_and_inventory_units_pass(self):
        self.workflow['moves'][0]['product_uom'] = [4, 'kg']
        self.assertEqual(self.verify()['order']['state'], 'purchase')

    def test_converted_quantity_mismatch_stops(self):
        self.workflow['moves'][0]['product_uom'] = [4, 'kg']
        self.workflow['moves'][0]['product_uom_qty'] = 8
        with self.assertRaisesRegex(RuntimeError, 'after UOM conversion'):
            self.verify()


class SupplierPreservationTests(unittest.TestCase):
    def setUp(self):
        self.variant = {'id': 20, 'product_tmpl_id': [30, 'Goods'], 'name': 'Goods', 'write_date': 'old', 'write_uid': [1, 'User']}
        self.template = {'id': 30, 'name': 'Goods', 'write_date': 'old', 'write_uid': [1, 'User']}
        self.addition = {'id': 50, 'product_tmpl_id': [30, 'Goods']}
        self.baseline = {'product.product': {'fields': list(self.variant), 'records': [self.variant]},
                         'product.template': {'fields': list(self.template), 'records': [self.template]},
                         'supplier_ids': [], 'settings': []}
        self.current_variant = dict(self.variant, write_date='new', write_uid=[2, 'Admin'])
        self.current_template = dict(self.template, write_date='new', write_uid=[2, 'Admin'])
        self.reader = Mock()
        self.reader.call.return_value = [50]
        def read(model, ids, fields):
            return {'product.product': [self.current_variant], 'product.template': [self.current_template],
                    'product.supplierinfo': [self.addition], 'res.company': []}[model]
        self.reader.read.side_effect = read

    def test_supplier_addition_allows_only_product_metadata(self):
        runner.verify_master(self.reader, self.baseline, [self.addition])

    def test_product_name_change_stops_even_with_supplier_permission(self):
        self.current_variant['name'] = 'Other goods'
        with self.assertRaisesRegex(RuntimeError, 'Master data changed'):
            runner.verify_master(self.reader, self.baseline, [self.addition])

    def test_unapproved_supplier_stops(self):
        self.reader.call.return_value = [50, 51]
        with self.assertRaisesRegex(RuntimeError, 'Unreviewed supplier'):
            runner.verify_master(self.reader, self.baseline, [self.addition])


if __name__ == '__main__':
    unittest.main()
