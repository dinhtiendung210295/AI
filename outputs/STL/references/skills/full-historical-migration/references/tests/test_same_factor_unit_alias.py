import copy
import runpy
import unittest
from pathlib import Path
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'same_factor_unit_alias.py'))
class Tests(unittest.TestCase):
    def units(self):return {14:{'id':14,'factor':1.,'rounding':.01,'relative_factor':1.,'relative_uom_id':False},15:{'id':15,'factor':1000.,'rounding':.01,'relative_factor':1000.,'relative_uom_id':[14,'g']},462:{'id':462,'factor':1000.,'rounding':.01,'relative_factor':1000.,'relative_uom_id':[14,'g']}}
    def test_same_factor_root_and_precision_prove_quantity_one_to_one(self):
        units=self.units();proof=M['prove'](462,15,units)
        self.assertEqual(proof['quantity_conversion'],1);self.assertEqual(proof['root_unit'],14)
        self.assertEqual(M['check'](proof,462,15,units),proof)
    def test_different_dimension_not_an_alias(self):
        units=self.units();units[462]['relative_uom_id']=False
        with self.assertRaises(ValueError):M['prove'](462,15,units)
    def test_different_conversion_not_an_alias(self):
        units=self.units();units[462]['factor']=1.
        with self.assertRaises(ValueError):M['prove'](462,15,units)
    def test_different_precision_not_accepted(self):
        units=self.units();units[462]['rounding']=.001
        with self.assertRaises(ValueError):M['prove'](462,15,units)
    def test_missing_or_cyclic_root_not_accepted(self):
        for cycle in [False,True]:
            units=self.units()
            if cycle:units[14]['relative_uom_id']=[462,'KG']
            else:del units[14]
            with self.subTest(cycle=cycle),self.assertRaises(ValueError):M['prove'](462,15,units)
    def test_changed_live_metadata_or_tampered_evidence_not_accepted(self):
        units=self.units();proof=M['prove'](462,15,units);proof['quantity_conversion']=1000
        with self.assertRaises(ValueError):M['check'](proof,462,15,units)
if __name__=='__main__':unittest.main()
