import runpy
import unittest
from pathlib import Path
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'migrate_pysb_independent_mos.py'))
Run=M['Run']

class Tests(unittest.TestCase):
    def make(self,status=None):
        r=Run.__new__(Run);r.mos={2:{'name':'MO2'}};r.j={'mos':{} if status is None else {'2':{'status':status}}}
        r.plan={'rows':[{'source_mo':1,'event_utc':'2026-08-01','eligible':True}]}
        r.a=type('NoRPC',(),{'read':lambda *a: self.fail('Must stop before any source or mutation RPC')})()
        return r
    def test_verified_mo_is_not_consumed_again(self):
        self.make('verified_done').process({'source_mo':2,'eligible':True})
    def test_mark_done_interruption_requires_readback(self):
        with self.assertRaisesRegex(RuntimeError,'read-back recovery'):
            self.make('done_pending_verification').process({'source_mo':2,'eligible':True})
    def test_prepared_raw_moves_are_not_consumed_blindly_again(self):
        with self.assertRaisesRegex(RuntimeError,'read-back recovery'):
            self.make('prepared_unconsumed').process({'source_mo':2,'eligible':True})
    def test_future_proposed_supply_cannot_be_used(self):
        with self.assertRaisesRegex(RuntimeError,'Earlier proposed MO supply not completed'):
            self.make().process({'source_mo':2,'event_utc':'2026-08-02','eligible':True})

if __name__=='__main__':unittest.main()
