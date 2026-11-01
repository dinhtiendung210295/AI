import runpy
from pathlib import Path
import unittest

M = runpy.run_path(str(Path(__file__).parents[1] / 'confirm_pysb_approved_supplier_pos.py'))

class Tests(unittest.TestCase):
    def fixture(self):
        prior = {10: {'id': 10, 'price': 5}}
        info = dict(id=11, partner_id=[5, 'Vendor'], product_tmpl_id=[20, 'Template'], product_id=False, currency_id=[7, 'CNY'], company_id=[1, 'Company'], min_qty=1, delay=0)
        return [{1: dict(id=1, seller_ids=[10], active=True)}, [dict(id=1, seller_ids=[10,11], active=True)], prior, {10: dict(prior[10]), 11: info}, {1: {'product_tmpl_id': [20,'Template']}}, {1}, 5, 7]

    def test_native_addition(self):
        self.assertEqual([11], M['validate_delta'](*self.fixture()))

    def test_existing_supplier_change_refused(self):
        args=self.fixture();args[3][10]['price']=6
        with self.assertRaises(RuntimeError):M['validate_delta'](*args)

    def test_wrong_identity_refused(self):
        for field,value in [('partner_id',[6,'Other']),('product_tmpl_id',[21,'Other']),('currency_id',[1,'USD']),('company_id',[2,'Other']),('product_id',[2,'Other'])]:
            args=self.fixture();args[3][11][field]=value
            with self.subTest(field=field), self.assertRaises(RuntimeError):M['validate_delta'](*args)

    def test_unapproved_product_refused(self):
        args=self.fixture();args[5]=set()
        with self.assertRaises(RuntimeError):M['validate_delta'](*args)

    def test_unapproved_po_refused(self):
        runner=M['ApprovedPO'].__new__(M['ApprovedPO']);runner.allowed={1:{'target_id':2}}
        with self.assertRaises(RuntimeError):runner.preflight({'source_id':3,'target_id':4})
