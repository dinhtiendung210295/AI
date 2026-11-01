"""Offline regression for production SO workflow holds."""
import copy
import runpy
import unittest
from pathlib import Path

M = runpy.run_path(str(Path(__file__).parents[1] / 'confirm_pysb_prod_so.py'))


class TestSOHolds(unittest.TestCase):
    def setUp(self):
        self.order = dict(warehouse_id=[1, 'HQ'], partner_id=1, partner_invoice_id=1, partner_shipping_id=1, picking_ids=[])
        self.line = dict(product_id=2, product_uom_id=3, warehouse_id=1, base_price=10)
        self.args = [self.order, [self.line], {2: dict(active=True, type='consu', route_ids=[4, 5], categ_id=7)}, {1: dict(active=True, property_stock_customer=2)}, {7: dict(total_route_ids=[])}, {3: {}}, {}, dict(ready=True)]

    def issues(self):
        return M['workflow_issues'](*self.args)

    def test_verified_mts(self):
        self.assertEqual([], self.issues())

    def test_credit_approval_held(self):
        self.order['x_need_so_approval'] = True
        self.assertIn('native_approval_required', self.issues())

    def test_procurement_override_held(self):
        self.line['route_ids'] = [99]
        self.assertIn('line_procurement_override', self.issues())

    def test_product_manufacture_route_held(self):
        self.args[2][2]['route_ids'] = [99]
        self.assertIn('product_route_unproven', self.issues())

    def test_zero_base_price_needs_free_flag(self):
        self.line['base_price'] = 0
        self.assertIn('zero_base_price_not_free', self.issues())
        self.line['is_free'] = True
        self.assertEqual([], self.issues())

    def test_draft_existing_chain_held(self):
        self.order['picking_ids'] = [123]
        self.assertIn('draft_already_has_pickings', self.issues())

    def test_carrier_and_archived_partner_held(self):
        self.order['carrier_id'] = 9
        self.args[3][1]['active'] = False
        self.assertIn('carrier_requires_review', self.issues())
        self.assertIn('archived_or_missing_partner', self.issues())

    def test_exact_historical_archived_shipping_can_stay_archived(self):
        self.order.update(id=5136,partner_shipping_id=81759)
        fields=dict(name='GENTING',type='delivery',street='historical street',street2=False,city='GENTING',zip='69000',phone='03-61011118')
        self.args[3][81759]=dict(fields,active=False,property_stock_customer=2)
        self.args[-1].update(historical_archived_shipping={5136:81759},historical_archived_shipping_source=dict(fields,id=27120,active=False))
        self.assertEqual([],self.issues())
        self.args[3][81759]['street']='different address'
        self.assertIn('archived_or_missing_partner',self.issues())


if __name__ == '__main__': unittest.main()
