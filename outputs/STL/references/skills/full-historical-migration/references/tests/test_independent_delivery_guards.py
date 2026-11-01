import copy
import runpy
import unittest
from pathlib import Path
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'migrate_pysb_independent_deliveries.py'))
Run=M['Run']

class Tests(unittest.TestCase):
    def fixture(self,sourceqty=2,targetqty=2):
        r=Run.__new__(Run);r.maps={'sale.order.line':{10:20},'product.product':{1:101},'uom.uom':{1:1}};r.tp={101:{'type':'consu'}};r.tu={1:{'rounding':0.01}};r.j={};r.persist=lambda:None
        source={'id':10,'product_id':[1,'P'],'product_uom':[1,'Unit'],'qty_delivered':sourceqty,'product_uom_qty':sourceqty,'price_unit':1,'discount':0,'price_subtotal':sourceqty,'price_total':sourceqty}
        target={**source,'id':20,'product_id':[101,'P'],'product_uom_id':[1,'Unit'],'qty_delivered':targetqty}
        def read(model,ids,fields):
            self.assertEqual(model,'sale.order.line');self.assertEqual(ids,[20]);return [target]
        r.b=type('Reader',(),{'read':staticmethod(read)})();g={'target_lines':[target],'source_lines':[source]}
        return r,g
    def test_so_uses_sale_lines_not_purchase_lines(self):
        r,g=self.fixture();r.verify_order_fulfillment(g)
    def test_delivered_shortage_still_fails(self):
        r,g=self.fixture(2,1)
        with self.assertRaisesRegex(RuntimeError,'qty_delivered'):r.verify_order_fulfillment(g)
    def test_approved_rounding_logged_per_order_line(self):
        r,g=self.fixture(0.62448,0.62);r.verify_order_fulfillment(g)
        self.assertEqual(r.j['order_rounding_differences'][0]['source_line'],10)
    def test_interrupted_preparation_never_confirms_again(self):
        r=Run.__new__(Run);r.j={'groups':{'1':{'phase':'order_confirmed'}}}
        with self.assertRaisesRegex(RuntimeError,'read-back'):r.prepare({'source':{'id':1},'target':{'id':2}})
    def test_resume_cannot_prepare_stock_for_draft_so(self):
        r=Run.__new__(Run);r.b=type('Reader',(),{'read':staticmethod(lambda *a:[{'id':2,'state':'draft','company_id':[1,'P']}])})()
        r.target_chain=lambda *a:self.fail('No stock query or creation before real confirmation')
        with self.assertRaisesRegex(RuntimeError,'really be confirmed'):r.prepare_native_chain({'target':{'id':2}}, {})

if __name__=='__main__':unittest.main()
