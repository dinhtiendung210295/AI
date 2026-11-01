import runpy
import unittest
from pathlib import Path
adjust=runpy.run_path(str(Path(__file__).resolve().parents[1]/'approved_stock_rounding.py'))['adjusted_source']

class Tests(unittest.TestCase):
    def run_adjust(self,precision,target):
        move={'product_uom':[1,'Roll'],'quantity_done':0.62448}
        lines=[{'id':10,'product_uom_id':[1,'Roll'],'qty_done':0.62448}]
        records={10:{'source_line':10,'source_qty':0.62448,'target_qty':target,'target_unit':11}}
        return adjust(move,lines,records,{'uom.uom':{1:11}},{1:{'factor':1}},{11:{'rounding':precision}})
    def test_roll_precision_is_exactly_applied(self):
        move,lines,records=self.run_adjust(0.01,0.62)
        self.assertEqual(move['quantity_done'],0.62);self.assertEqual(lines[0]['qty_done'],0.62)
    def test_finer_unit_precision_has_its_own_expected_value(self):
        self.assertEqual(self.run_adjust(0.0001,0.6245)[0]['quantity_done'],0.6245)
    def test_nearby_but_unapproved_difference_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'UoM policy'):self.run_adjust(0.01,0.621)

if __name__=='__main__':unittest.main()
