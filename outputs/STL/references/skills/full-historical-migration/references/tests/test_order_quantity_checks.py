import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('checks', Path(__file__).resolve().parents[1] / 'order_quantity_checks.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Checks(unittest.TestCase):
    def setUp(self):
        self.source = {'id': 1, 'product_id': [3, 'Service'], 'product_uom': [4, 'Unit'], 'display_type': False,
                       'product_uom_qty': 10, 'qty_delivered': 6, 'qty_invoiced': 4}
        self.target = {**self.source, 'id': 2, 'product_id': [30, 'Service'], 'product_uom': [40, 'Unit']}
        self.maps = {'sale.order.line': {1: 2}, 'product.product': {3: 30}, 'uom.uom': {4: 40}}

    def check(self):
        return m.compare_lines('sale.order.line', [self.source], [self.target], self.maps,
                               {4: {'rounding': 0.01}}, {40: {'rounding': 0.01}})['rows'][0]

    def test_partial_delivery_and_invoice_service(self):
        self.assertTrue(self.check()['match'])
        self.target['qty_invoiced'] = 0
        self.assertFalse(self.check()['metrics']['invoiced']['match'])

    def test_ordered_mismatch_blocks(self):
        self.target['product_uom_qty'] = 11
        self.assertFalse(self.check()['match'])

    def test_missing_mapping_is_retained(self):
        self.maps['sale.order.line'] = {}
        self.assertFalse(self.check()['match'])

    def test_wrong_unit_cannot_pass_equal_quantities(self):
        self.target['product_uom'] = [41, 'Box']
        self.assertFalse(self.check()['match'])

    def test_returns_and_refunds_net_quantity(self):
        self.source['qty_delivered'] = self.target['qty_delivered'] = -2
        self.source['qty_invoiced'] = self.target['qty_invoiced'] = -1
        self.assertTrue(self.check()['match'])

    def test_per_unit_rounding(self):
        self.assertTrue(m.quantity_check(3.3333, 3.33, 0.01)['match'])
        self.assertFalse(m.quantity_check(3.3333, 3.33, 0.0001)['match'])
        self.assertFalse(m.quantity_check(1, 1, None)['match'])

    def test_missing_field_fails(self):
        del self.target['qty_invoiced']
        self.assertFalse(self.check()['match'])

    def test_wrong_order_link_blocks(self):
        self.source['order_id']=[8,'SO source']
        self.target['order_id']=[81,'Wrong SO']
        self.maps['sale.order']={8:80}
        self.assertFalse(self.check()['match'])

    def test_shared_target_line_blocks(self):
        source2={**self.source,'id':9}
        self.maps['sale.order.line'][9]=2
        report=m.compare_lines('sale.order.line',[self.source,source2],[self.target],self.maps,
                               {4:{'rounding':0.01}},{40:{'rounding':0.01}})
        self.assertEqual(report['summary']['matched'],0)

    def test_po_received_and_invoiced(self):
        source = {**self.source, 'product_qty': 10, 'qty_received': 6}
        target = {**self.target, 'product_qty': 10, 'qty_received': 5}
        maps = {**self.maps, 'purchase.order.line': {1: 2}}
        report = m.compare_lines('purchase.order.line', [source], [target], maps,
                                 {4: {'rounding': 0.01}}, {40: {'rounding': 0.01}})
        self.assertFalse(report['rows'][0]['metrics']['received']['match'])

    def test_missing_mapping_still_has_every_source_metric(self):
        self.maps['sale.order.line']={};row=self.check()
        self.assertEqual(set(row['metrics']),{'ordered','delivered','invoiced'})
        self.assertEqual(row['metrics']['delivered']['source'],6)
        self.assertIsNone(row['metrics']['delivered']['target']);self.assertIsNone(row['metrics']['delivered']['delta'])
        self.assertFalse(row['metrics']['delivered']['match'])
    def test_finer_target_precision_is_not_hidden_by_source_precision(self):
        self.target['qty_delivered']=6.4
        row=m.compare_lines('sale.order.line',[self.source],[self.target],self.maps,{4:{'rounding':1}},{40:{'rounding':.01}})['rows'][0]
        self.assertEqual(row['unit_precision']['comparison'],.01);self.assertFalse(row['metrics']['delivered']['match'])
    def test_identity_metrics_have_source_expected_and_actual_target(self):
        row=self.check();self.assertEqual(row['identity']['product']['source'],3)
        self.assertEqual(row['identity']['product']['expected_target'],30)
        self.assertEqual(row['identity']['product']['target'],30);self.assertTrue(row['identity']['product']['match'])

    def test_equal_numbers_with_wrong_unit_are_not_quantity_passes(self):
        self.target['product_uom']=[41,'Different unit'];row=self.check()
        self.assertFalse(row['metrics']['delivered']['match']);self.assertIsNone(row['metrics']['delivered']['delta'])
        self.assertEqual(row['metrics']['delivered']['raw_numeric_delta'],0)
    def test_same_factor_same_precision_alias_is_an_exact_unit_match(self):
        self.target['product_uom']=[41,'kg']
        target_units={39:{'id':39,'factor':1,'rounding':.01,'relative_factor':1,'relative_uom_id':False},40:{'id':40,'factor':1000,'rounding':.01,'relative_factor':1000,'relative_uom_id':39},41:{'id':41,'factor':1000,'rounding':.01,'relative_factor':1000,'relative_uom_id':39}}
        row=m.compare_lines('sale.order.line',[self.source],[self.target],self.maps,{4:{'rounding':.01}},target_units)['rows'][0]
        self.assertTrue(row['match']);self.assertEqual(row['identity']['unit']['same_factor_alias_proof']['quantity_conversion'],1)
    def test_wrong_product_does_not_pass_equal_raw_quantity(self):
        self.target['product_id']=[31,'Other'];row=self.check()
        self.assertFalse(row['metrics']['ordered']['match']);self.assertEqual(row['metrics']['ordered']['reason'],'product_identity_unverified')

if __name__ == '__main__':
    unittest.main()
