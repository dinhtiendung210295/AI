import runpy
from pathlib import Path
import unittest

M=runpy.run_path(str(Path(__file__).parents[1]/'complete_pysb_authorized_po_gaps.py'))

class Tests(unittest.TestCase):
    def fixture(self):
        header=dict(id=1,name='PO-SOURCE',company_id=[1,'Company'],partner_id=[2,'Vendor'],currency_id=[3,'MYR'],payment_term_id=False,picking_type_id=[4,'Receipt'],user_id=[5,'Buyer'],date_order='2026-01-01 00:00:00',date_approve='2026-01-02 00:00:00',partner_ref='VENDOR-REF',notes='terms',attn='Buyer')
        line=dict(id=10,sequence=1,name='Historical line',display_type=False,product_id=[6,'P'],product_uom=[7,'UNIT'],product_qty=3,price_unit=5,date_planned='2026-02-01 00:00:00',taxes_id=[])
        maps={m:{sid:tid} for m,sid,tid in [('res.partner',2,20),('res.currency',3,30),('stock.picking.type',4,40),('res.users',5,50),('product.product',6,60),('uom.uom',7,70)]}
        return header,[line],maps

    def test_preserves_source_dates_and_explicit_empty_taxes(self):
        values=M['create_values'](*self.fixture())
        self.assertEqual('2026-01-01 00:00:00',values['date_order'])
        self.assertEqual('2026-01-02 00:00:00',values['x_studio_date_ref_v14_studio'])
        self.assertEqual([(6,0,[])],values['order_line'][0][2]['tax_ids'])
        self.assertNotIn('state',values)
        self.assertIn('note',values)
        self.assertNotIn('notes',values)

    def test_missing_product_never_defaults(self):
        h,l,m=self.fixture();m['product.product']={}
        with self.assertRaises(RuntimeError):M['create_values'](h,l,m)

    def test_note_line_preserved_without_product(self):
        h,l,m=self.fixture();l.append(dict(id=11,sequence=2,display_type='line_note',name='Historical note'))
        values=M['create_values'](h,l,m)
        self.assertEqual('line_note',values['order_line'][1][2]['display_type'])
        self.assertNotIn('product_id',values['order_line'][1][2])
        self.assertEqual(0,values['order_line'][1][2]['product_qty'])

    def test_buyer_payment_term_and_supplier_not_defaulted(self):
        h,l,m=self.fixture();h['payment_term_id']=[8,'30 Days']
        with self.assertRaises(RuntimeError):M['create_values'](h,l,m)
        m['account.payment.term']={8:80}
        values=M['create_values'](h,l,m)
        self.assertEqual((20,50,80),(values['partner_id'],values['user_id'],values['payment_term_id']))
