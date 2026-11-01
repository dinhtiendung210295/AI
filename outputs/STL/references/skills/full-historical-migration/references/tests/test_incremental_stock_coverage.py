import runpy,unittest
from pathlib import Path
M=runpy.run_path(str(Path(__file__).parents[1]/'check_pysb_aug_oct_coverage.py'))
class Tests(unittest.TestCase):
    def test_new_changed_unresolved_and_missing_cached_targets_are_read(self):
        maps={'stock.move':{1:11,2:22,3:33,4:44,5:55}}
        previous=dict(scan_complete=True,schema_version=2,results=[dict(source_move_id=1,target_move_id=11,status='verified'),dict(source_move_id=2,target_move_id=22,status='unresolved'),dict(source_move_id=3,target_move_id=99,status='verified'),dict(source_move_id=4,target_move_id=44,status='approved_exception')])
        self.assertEqual(M['incremental_selection'](maps,[{'id':i} for i in range(1,6)],previous,[{'id':i} for i in [11,22,33,55]]),{22,33,44,55})
    def test_incomplete_baseline_rejected(self):
        with self.assertRaises(RuntimeError):M['incremental_selection']({},[],dict(scan_complete=False,schema_version=2),[])
if __name__=='__main__':unittest.main()
