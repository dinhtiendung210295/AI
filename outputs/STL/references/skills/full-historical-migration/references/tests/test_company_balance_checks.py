import copy
import runpy
import unittest
from pathlib import Path
F=runpy.run_path(str(Path(__file__).resolve().parents[1]/'company_balance_checks.py'))['compare']


class Tests(unittest.TestCase):
    def fixture(self):
        s={'id':11,'product_id':1,'product_uom_id':1,'location_id':10,'location_dest_id':12,'lot_id':7,'package_id':False,'result_package_id':False,'owner_id':False,'date':'2026-08-02','qty_done':.62448}
        t=dict(s,id=111,product_id=101,product_uom_id=201,location_id=20,location_dest_id=22,lot_id=77,quantity=.62);del t['qty_done']
        a={'products':[{'id':1,'uom_id':1}],'units':[{'id':1,'factor':1,'rounding':.00001}],'done_lines':[s],
           'balances':{'2026-08-01':[{'key':[1,10,7,False,False],'quantity':1}], '2026-08-03':[{'key':[1,10,7,False,False],'quantity':.37552}]}}
        b={'products':[{'id':101,'uom_id':201}],'units':[{'id':201,'factor':1,'rounding':.01}],'done_lines':[t],
           'balances':{'2026-08-01':[{'key':[101,20,77,False,False],'quantity':1}], '2026-08-03':[{'key':[101,20,77,False,False],'quantity':.38}]}}
        maps={'product.product':{'1':101},'uom.uom':{'1':201},'stock.location':{'10':20,'12':22},'stock.lot':{'7':77},'stock.move.line':{'11':111}}
        records={11:{'source_quantity':.62448,'target_quantity':.62,'target_unit':201}}
        return a,b,maps,records

    def test_approved_consumption_delta_is_separate_from_raw_match(self):
        report=F(*self.fixture());opening=report['2026-08-01']['rows'][0];closing=report['2026-08-03']['rows'][0]
        self.assertTrue(opening['matched']);self.assertEqual(opening['approved_rounding_delta'],0)
        self.assertFalse(closing['matched']);self.assertTrue(closing['approved_exception'])
        self.assertEqual(closing['source_mapped_quantity'],.37552)
        self.assertAlmostEqual(closing['approved_rounding_delta'],.00448)
        self.assertEqual(closing['comparison_precision'],.00001)

    def test_target_precision_alone_does_not_hide_unapproved_difference(self):
        a,b,maps,records=self.fixture();report=F(a,b,maps,{})
        self.assertEqual(report['2026-08-03']['summary']['different'],1)

    def test_wrong_captured_quantity_or_dimensions_rejected(self):
        for field,value in [('quantity',.63),('lot_id',78)]:
            a,b,maps,records=self.fixture();b['done_lines'][0][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):F(a,b,maps,records)

    def test_missing_mapping_is_retained(self):
        a,b,maps,records=self.fixture();maps['stock.lot']={};report=F(a,b,maps,{})
        self.assertEqual(report['2026-08-03']['summary']['unmapped_source_keys'],1)
        self.assertEqual(report['2026-08-03']['missing_source_keys'][0]['quantity'],.37552)

    def test_future_rounding_cannot_explain_earlier_balance(self):
        a,b,maps,records=self.fixture();a['done_lines'][0]['date']=b['done_lines'][0]['date']='2026-08-03'
        row=F(a,b,maps,records)['2026-08-03']['rows'][0]
        self.assertFalse(row['approved_exception']);self.assertEqual(row['approved_rounding_delta'],0)

    def test_same_factor_native_alias_keeps_quantities_and_source_precision(self):
        a,b,maps,records=self.fixture();maps['uom.uom']['1']=202
        b['units']=[{'id':200,'factor':1,'rounding':.01,'relative_factor':1,'relative_uom_id':False},{'id':201,'factor':1000,'rounding':.01,'relative_factor':1000,'relative_uom_id':200},{'id':202,'factor':1000,'rounding':.01,'relative_factor':1000,'relative_uom_id':200}]
        report=F(a,b,maps,{})['2026-08-01']
        self.assertEqual(report['summary']['unmapped_source_keys'],0)
        self.assertTrue(report['rows'][0]['matched']);self.assertEqual(report['rows'][0]['comparison_precision'],.00001)
        self.assertEqual(len(report['base_unit_alias_proofs']),1)
    def test_source_with_unproven_unit_not_hidden_by_another_source_product(self):
        a,b,maps,records=self.fixture();a['products'].append({'id':2,'uom_id':2});a['units'].append({'id':2,'factor':1,'rounding':.00001})
        a['balances']['2026-08-01'].append({'key':[2,10,7,False,False],'quantity':3});maps['product.product']['2']=101
        report=F(a,b,maps,{})['2026-08-01']
        self.assertEqual(report['summary']['unmapped_source_keys'],1)
        self.assertEqual(report['missing_source_keys'][0]['key'][0],2)


if __name__=='__main__':unittest.main()
