import runpy
from pathlib import Path
import unittest

M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'migrate_pysb_independent_receipts.py'))

class UnitChecks(unittest.TestCase):
    def setUp(self):
        self.units={1:{'factor':1,'relative_uom_id':False},14:{'factor':1,'relative_uom_id':False},15:{'factor':1000,'relative_uom_id':[14,'g']},462:{'factor':1000,'relative_uom_id':[14,'g']},3:{'factor':12,'relative_uom_id':[1,'Units']}}
    def test_kg_alias_same_quantity(self):self.assertTrue(M['equivalent_demand'](15,25.8,462,25.8,self.units))
    def test_partial_receipt_not_equivalent(self):self.assertFalse(M['equivalent_demand'](1,3,1,1,self.units))
    def test_different_unit_families_blocked(self):self.assertFalse(M['equivalent_demand'](1,1,14,1,self.units))
    def test_exact_pack_conversion(self):self.assertTrue(M['equivalent_demand'](3,1,1,12,self.units))

if __name__=='__main__':unittest.main()
