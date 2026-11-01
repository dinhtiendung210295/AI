import unittest,runpy
from pathlib import Path
M=runpy.run_path(str(Path(__file__).parents[1]/'receipt_service_line.py'))
class Tests(unittest.TestCase):
    def test_only_nonphysical_service_can_skip_receipt_requirement(self):
        f=M['nonphysical_service'];s=dict(id=1,qty_received=0);t=dict(id=2);service=dict(type='service')
        self.assertTrue(f(s,t,service,service,[]))
        for source,target,moves in [(dict(type='product'),service,[]),(service,dict(type='consu'),[]),(service,service,[dict(purchase_line_id=1)])]:self.assertFalse(f(s,t,source,target,moves))
        self.assertFalse(f(dict(id=1,qty_received=1),t,service,service,[]))
        self.assertFalse(f(s,None,service,service,[]))
if __name__=='__main__':unittest.main()
