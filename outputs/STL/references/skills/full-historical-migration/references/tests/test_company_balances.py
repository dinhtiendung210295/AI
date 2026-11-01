import runpy
import unittest
from pathlib import Path

F=runpy.run_path(str(Path(__file__).resolve().parents[1]/'inspect_pysb_company_balances.py'))['balances']


class Tests(unittest.TestCase):
    def test_boundaries_and_package_transfer(self):
        quants=[dict(product_id=1,location_id=2,lot_id=3,package_id=5,owner_id=6,quantity=7)]
        lines=[dict(product_id=1,product_uom_id=1,location_id=1,location_dest_id=2,lot_id=3,
                    package_id=4,result_package_id=5,owner_id=6,date='2026-09-01',qty_done=7)]
        result=F(quants,lines,{1:{'uom_id':1}},{1:{'factor':1}},{1:{'usage':'internal'},2:{'usage':'internal'}},['2026-09-01','2026-09-02'],True)
        self.assertEqual(result['2026-09-01'],[{'key':[1,1,3,4,6],'quantity':7}])
        self.assertEqual(result['2026-09-02'],[{'key':[1,2,3,5,6],'quantity':7}])

    def test_version_specific_unit_conversion(self):
        common=dict(product_id=1,product_uom_id=2,location_id=1,location_dest_id=2,lot_id=False,
                    package_id=False,result_package_id=False,owner_id=False,date='2026-09-01')
        loc={1:{'usage':'internal'},2:{'usage':'supplier'}}
        for source,factor,quantity in [(True,.5,'qty_done'),(False,2,'quantity')]:
            result=F([], [dict(common,**{quantity:3})],{1:{'uom_id':1}},
                     {1:{'factor':1},2:{'factor':factor}},loc,['2026-09-01'],source)
            self.assertEqual(result['2026-09-01'],[{'key':[1,1,False,False,False],'quantity':6}])

    def test_historical_cutoff_uses_parent_move_date(self):
        line=dict(product_id=1,product_uom_id=1,location_id=1,location_dest_id=2,lot_id=False,
                  package_id=False,result_package_id=False,owner_id=False,date='2026-09-01',move_date='2026-09-02',qty_done=3)
        result=F([], [line],{1:{'uom_id':1}},{1:{'factor':1}},
                 {1:{'usage':'internal'},2:{'usage':'supplier'}},['2026-09-01','2026-09-02','2026-09-03'],True)
        self.assertEqual(result['2026-09-01'],result['2026-09-02'])
        self.assertEqual(result['2026-09-03'],[])

    def test_nonstock_goods_do_not_create_phantom_historical_quants(self):
        line=dict(product_id=1,product_uom_id=1,location_id=1,location_dest_id=2,lot_id=False,package_id=False,result_package_id=False,owner_id=False,date='2026-09-01',qty_done=5,quantity=5,quantity_product_uom=5)
        loc={1:{'usage':'internal'},2:{'usage':'customer'}}
        for source,product in [(True,{'uom_id':1,'type':'consu'}),(False,{'uom_id':1,'is_storable':False})]:
            result=F([], [line],{1:product},{1:{'factor':1,'rounding':1}},loc,['2026-08-01'],source)
            self.assertEqual(result['2026-08-01'],[])
    def test_source_conversion_uses_product_base_precision(self):
        line=dict(product_id=1,product_uom_id=2,location_id=1,location_dest_id=2,lot_id=False,package_id=False,result_package_id=False,owner_id=False,date='2026-09-01',qty_done=20)
        result=F([], [line],{1:{'uom_id':1,'type':'product'}},{1:{'factor':1/30,'rounding':.00001},2:{'factor':1,'rounding':.00001}},{1:{'usage':'internal'},2:{'usage':'customer'}},['2026-08-01'],True)
        self.assertAlmostEqual(result['2026-08-01'][0]['quantity'],.66667)
    def test_target_undo_uses_captured_actual_base_quantity(self):
        line=dict(product_id=1,product_uom_id=2,location_id=1,location_dest_id=2,lot_id=False,package_id=False,result_package_id=False,owner_id=False,date='2026-09-01',quantity=20,quantity_product_uom=.67)
        result=F([], [line],{1:{'uom_id':1,'is_storable':True}},{1:{'factor':30,'rounding':.01},2:{'factor':1,'rounding':.01}},{1:{'usage':'internal'},2:{'usage':'customer'}},['2026-08-01'],False)
        self.assertEqual(result['2026-08-01'][0]['quantity'],.67)


if __name__=='__main__':unittest.main()
