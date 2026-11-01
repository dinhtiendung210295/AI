import runpy,unittest
from pathlib import Path
M=runpy.run_path(str(Path(__file__).parents[1]/'apply_pysb_safe_temporary_offsets.py'))
class Tests(unittest.TestCase):
    def test_later_count_must_match_real_source_not_just_a_mapping_id(self):
        source=dict(state='done',date='2026-07-20 00:00:00',company_id=[1,'P'],product_id=[10,'SKU']);target=dict(source)
        self.assertTrue(M['matching_source_event'](source,target,10,-2,-2))
        for altered in [dict(target,state='cancel'),dict(target,date='2026-07-21 00:00:00'),dict(target,company_id=[2,'Other'])]:self.assertFalse(M['matching_source_event'](source,altered,10,-2,-2))
        self.assertFalse(M['matching_source_event'](source,target,99,-2,-2));self.assertFalse(M['matching_source_event'](source,target,10,-2,-1))
    def test_count_only_removes_proven_excess(self):self.assertEqual(M['count_gate'](M['KEYS'][0],-1,1,0,0,1),0)
    def test_negative_reserved_unknown_or_unexplained_is_rejected(self):
        cases=[(M['KEYS'][0],-1,0,0,0,1),(M['KEYS'][0],-1,1,1,0,1),((999,5,1,False,False),-1,1,0,0,1),(M['KEYS'][0],-2,2,0,0,2),(M['KEYS'][0],-1,1,0,0,2)]
        for args in cases:
            with self.assertRaises(RuntimeError):M['count_gate'](*args)
    def test_direct_quantity_or_foreign_quant_write_never_reaches_rpc(self):
        r=M['Run'].__new__(M['Run']);r.entry=dict(quant_id=1,count_after=0,reference='test');r.b=type('Reader',(),{'r':type('Identity',(),{'uid':7})()})()
        for args in [[[1],{'quantity':0}],[[2],{'inventory_quantity':0,'user_id':7}]]:
            with self.assertRaisesRegex(RuntimeError,'allowlist'):r.mutate('stock.quant','write',args)
if __name__=='__main__':unittest.main()
