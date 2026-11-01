import runpy,unittest
from pathlib import Path
F=runpy.run_path(str(Path(__file__).resolve().parents[1]/'delivery_stage_demand.py'))['differs']
class Tests(unittest.TestCase):
    def data(self):
        moves=[{'product_id':10,'location_id':1,'location_dest_id':2,'product_uom':20,'product_uom_qty':3},{'product_id':10,'location_id':2,'location_dest_id':3,'product_uom':20,'product_uom_qty':3},{'product_id':10,'location_id':3,'location_dest_id':4,'product_uom':20,'product_uom_qty':3}]
        return moves,{1:{'usage':'internal'},2:{'usage':'internal'},3:{'usage':'internal'},4:{'usage':'customer'}},{'uom.uom':{20:100}},{100:{'factor':1},101:{'factor':30}}
    def test_equal_physical_stages_keep_proven_flow(self):self.assertFalse(F(*self.data()))
    def test_pick_six_delivery_three_requires_own_sample(self):
        args=self.data();args[0][0]['product_uom_qty']=6;self.assertTrue(F(*args))
    def test_units_compare_physical_quantity_not_labels(self):
        moves,loc,maps,units=self.data();maps['uom.uom'][21]=101
        for move in moves[:2]:move['product_uom_qty']=90
        moves[-1].update(product_uom=21,product_uom_qty=3)
        self.assertFalse(F(moves,loc,maps,units))
if __name__=='__main__':unittest.main()
