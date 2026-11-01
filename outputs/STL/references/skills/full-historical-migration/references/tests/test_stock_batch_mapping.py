import runpy
import unittest
from pathlib import Path
Run=runpy.run_path(str(Path(__file__).resolve().parents[1]/'migrate_pysb_independent_receipts.py'))['Run']

class Tests(unittest.TestCase):
    def make(self,existing):
        r=Run.__new__(Run);r.maps={};r.persist=lambda:None;r.writes=[]
        r.b=type('Reader',(),{'call':staticmethod(lambda *args:existing)})();r.mutate=lambda *args:r.writes.append(args)
        return r
    def test_existing_mapping_is_reused_and_only_missing_is_created(self):
        r=self.make([{'name':'stock_move_line_1','model':'stock.move.line','res_id':101}])
        r.attach_many('stock.move.line',[(1,101),(2,102)])
        self.assertEqual(r.maps['stock.move.line'],{1:101,2:102});self.assertEqual(len(r.writes[0][2][0]),1)
    def test_conflict_stops_before_any_write(self):
        r=self.make([{'name':'stock_move_line_1','model':'stock.move.line','res_id':999}])
        with self.assertRaisesRegex(RuntimeError,'conflict'):r.attach_many('stock.move.line',[(1,101)])
        self.assertFalse(r.writes)
    def test_shared_target_line_is_rejected(self):
        r=self.make([])
        with self.assertRaisesRegex(RuntimeError,'Non-unique'):r.attach_many('stock.move.line',[(1,101),(2,101)])
        self.assertFalse(r.writes)

if __name__=='__main__':unittest.main()
