import runpy
import unittest
from pathlib import Path
check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'migrate_pysb_independent_receipts.py'))['assert_exact_stock']

def quant(lot,qty,reserved=0):return {'product_id':[1,'P'],'location_id':[5,'Stock'],'lot_id':[lot,'Lot'],'quantity':qty,'reserved_quantity':reserved}

class Tests(unittest.TestCase):
    def test_another_lot_never_fills_the_required_lot(self):
        with self.assertRaisesRegex(RuntimeError,'exact lot/location'):check({(1,5,20):1},[quant(21,10)])
    def test_overreservation_guard_preserved(self):
        with self.assertRaisesRegex(RuntimeError,'over-reserved'):check({(1,5,20):1},[quant(20,2,3)])
    def test_duplicate_quants_for_same_exact_key_are_summed(self):
        check({(1,5,20):1},[quant(20,0.5,0.4),quant(20,0.5,0.4)])

if __name__=='__main__':unittest.main()
