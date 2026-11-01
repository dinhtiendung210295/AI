import runpy
import unittest
from pathlib import Path
M=runpy.run_path(str(Path(__file__).parents[1]/'production_so_route_proof.py'))

class TestPullProof(unittest.TestCase):
    def setUp(self):
        self.order=dict(warehouse_id=2,partner_shipping_id=7)
        self.line=dict(id=10,product_id=9,product_uom_id=1,warehouse_id=2,route_ids=[])
        self.proof=dict(warehouses={2:dict(route_ids=[8],lot_stock_id=20)},rules=[dict(id=1,active=True,action='pull',procure_method='make_to_stock',company_id=1,warehouse_id=2,route_id=8,location_src_id=20,location_dest_id=2)])
        self.args=[self.order,[self.line],{9:dict(type='consu',route_ids=[],categ_id=1)},{7:dict(property_stock_customer=2)},{1:dict(total_route_ids=[])},{1:{}},{},self.proof,{}]
    def test_penang_stock_delivery(self):
        self.assertEqual([],M['evaluate'](*self.args)[0])
    def test_buy_does_not_pass_pull_proof(self):
        self.proof['rules'][0]['action']='buy'
        self.assertIn('route_would_create_PO_or_MO',M['evaluate'](*self.args)[0])
    def test_wrong_stock_blocks(self):
        self.proof['rules'][0]['location_src_id']=5
        self.assertIn('stock_source_not_warehouse_stock',M['evaluate'](*self.args)[0])
    def test_ambiguous_rule_blocks(self):
        self.proof['rules'].append(dict(self.proof['rules'][0],id=2))
        self.assertIn('pull_rule_not_unique',M['evaluate'](*self.args)[0])
    def test_dropship_is_retained_for_PO_dependency_review(self):
        self.line['route_ids']=[126]
        self.assertIn('explicit_route_can_create_purchase_order_or_unproven_route',M['evaluate'](*self.args)[0])
    def test_consignment_must_have_source_route_identity(self):
        self.line['route_ids']=[83]
        self.assertIn('explicit_route_source_identity_unproven',M['evaluate'](*self.args)[0])

if __name__=='__main__':unittest.main()
