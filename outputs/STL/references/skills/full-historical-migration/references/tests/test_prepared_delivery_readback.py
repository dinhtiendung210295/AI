import runpy,unittest
from pathlib import Path
check=runpy.run_path(str(Path(__file__).parents[1]/'prepared_delivery_readback.py'))['check_attempts']
class Tests(unittest.TestCase):
    def test_no_validation_attempt_allows_staged_readback(self):check([],set([1]),set())
    def test_any_prior_attempt_for_pending_picking_is_not_retried(self):
        for status in ['returned','intent','uncertain']:
            with self.assertRaises(RuntimeError):check([dict(model='stock.picking',method='button_validate',args=[[1]],status=status)],{1},set())
    def test_already_verified_picking_is_skipped(self):check([dict(model='stock.picking',method='button_validate',args=[[1]],status='returned')],{1,2},{1})
if __name__=='__main__':unittest.main()
