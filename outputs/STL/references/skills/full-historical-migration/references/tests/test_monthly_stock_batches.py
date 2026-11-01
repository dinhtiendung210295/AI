import runpy,unittest
from pathlib import Path
from types import SimpleNamespace
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'native_picking_batch_pilot.py'))

class MonthlyTests(unittest.TestCase):
    def fixture(self,n=6):
        groups=[];sm={};sp={};states={};calls=[]
        for i in range(1,n+1):
            ids=[i,i+100,i+200];groups.append(dict(source={'id':i},moves=ids,pickings=ids))
            states[str(i)]=dict(phase='chain_prepared',completed_pickings=[])
            for level,mid in enumerate(ids):
                sm[mid]=dict(picking_id=mid,move_orig_ids=ids[level-1:level] if level else [],move_dest_ids=ids[level+1:level+2])
                sp[mid]=dict(date_done=f'2026-09-04 0{level+1}:00:00',picking_type_id=level+1)
        def finish(g,only_picking):
            state=states[str(g['source']['id'])];self.assertNotIn(only_picking,state['completed_pickings'])
            state['completed_pickings'].append(only_picking)
            if set(state['completed_pickings'])==set(g['pickings']):state['phase']='completed'
        r=SimpleNamespace(j={'groups':states,'native_batch_pilots':[]},sm=sm,sp=sp,finish=finish)
        return r,groups,calls

    def test_select_month_spans_days_and_malaysia_boundary(self):
        picks={1:{'date_done':'2026-08-31 16:00:00'},2:{'date_done':'2026-09-29 16:00:00'},3:{'date_done':'2026-09-30 16:00:00'}}
        rows=[{'pickings':[3]},{'pickings':[1,2]}]
        self.assertEqual(M['select_month'](rows,picks),('2026-09',[rows[1]]))
        with self.assertRaisesRegex(RuntimeError,'Cross-month'):M['select_month']([{'pickings':[2,3]}],picks)

    def test_ready_only_after_predecessor_completed(self):
        r,groups,_=self.fixture(1)
        self.assertEqual([x[1] for x in M['month_ready_events'](r,groups,'2026-09')],[1])
        r.finish(groups[0],only_picking=1)
        self.assertEqual([x[1] for x in M['month_ready_events'](r,groups,'2026-09')],[101])

    def test_root_sample_alone_does_not_prove_dependent_batch(self):
        r,groups,_=self.fixture(2)
        for state in r.j['groups'].values():state['phase']='completed'
        pilot=dict(stage_batch=True,dependent_stage=False,status='all_validated_and_historical_dates_restored',pickings=[{'source_so':1},{'source_so':2}])
        r.j['native_batch_pilots'].append(pilot)
        self.assertFalse(M['stage_batch_proven'](r));pilot['dependent_stage']=True
        self.assertTrue(M['stage_batch_proven'](r))
        r.j['groups']['2']['phase']='chain_prepared';self.assertFalse(M['stage_batch_proven'](r))

    def test_scheduler_samples_then_scales_and_never_repeats_stage(self):
        r,groups,calls=self.fixture()
        fn=M['finish_monthly'];old=fn.__globals__['validate']
        def validate(reader,chosen,grouped,month,stage_by_so):
            proven=M['stage_batch_proven'](reader)
            if not proven:self.assertEqual(len(chosen),2)
            pids=list(stage_by_so.values());self.assertEqual(len({reader.sp[p]['picking_type_id'] for p in pids}),1)
            dependent=any(reader.sm[p]['move_orig_ids'] for p in pids)
            pilot=dict(stage_batch=True,dependent_stage=dependent,status='all_validated_and_historical_dates_restored',pickings=[{'source_so':g['source']['id']} for g in chosen])
            for g in chosen:
                pid=stage_by_so[g['source']['id']]
                self.assertTrue(set(reader.sm[pid]['move_orig_ids'])<=set(reader.j['groups'][str(g['source']['id'])]['completed_pickings']))
                reader.finish(g,only_picking=pid)
            reader.j['native_batch_pilots'].append(pilot);calls.append(len(chosen))
        fn.__globals__['validate']=validate
        try:self.assertEqual(fn(r,groups,'2026-09'),8)
        finally:fn.__globals__['validate']=old
        self.assertEqual(calls,[2,2,2,2,2,2,2,4])
        self.assertTrue(all(x['phase']=='completed' and len(x['completed_pickings'])==3 for x in r.j['groups'].values()))

    def test_cross_chain_dependency_rejected_before_validate(self):
        r,groups,_=self.fixture(2);r.sm[2]['move_orig_ids']=[1]
        with self.assertRaisesRegex(RuntimeError,'Cross-chain'):M['finish_monthly'](r,groups,'2026-09')

    def test_live_native_predecessor_not_done_blocks_validate(self):
        r,groups,_=self.fixture(1);g=groups[0];s=r.j['groups']['1'];s.update(completed_pickings=[1],move_pairs={1:11,101:111,201:211},picking_pairs={1:21,101:121,201:221})
        r.j['operations']=[];r.by_move={101:[]};r.maps={};r.locations={};r.tp={};r.tu={}
        def read(model,ids,fields):
            if model=='stock.picking' and 'state' in fields:return [dict(id=121,state='confirmed',company_id=1,carrier_id=False,picking_type_id=2)]
            if model=='stock.picking':return [dict(id=121,move_ids=[111])]
            if ids==[111]:return [dict(id=111,state='confirmed',company_id=1,move_orig_ids=[11],move_dest_ids=[211])]
            return [dict(id=11,state='confirmed',company_id=1)]
        r.b=SimpleNamespace(read=read)
        fn=M['validate'];old=fn.__globals__['prepare_root_details_together'];fn.__globals__['prepare_root_details_together']=lambda *args:None
        # Two independent chains required; the second has identical gates with distinct IDs.
        r2,gs,_=self.fixture(2);g2=gs[1];r.sm.update(r2.sm);r.sp.update(r2.sp);r.by_move[102]=[]
        r.j['groups']['2']=dict(phase='chain_prepared',completed_pickings=[2],move_pairs={2:12,102:112,202:212},picking_pairs={2:22,102:122,202:222})
        def reads(model,ids,fields):
            if model=='stock.picking' and 'state' in fields:return [dict(id=i,state='confirmed',company_id=1,carrier_id=False,picking_type_id=2) for i in ids]
            if model=='stock.picking':return [dict(id=i,move_ids=[i-10]) for i in ids]
            if ids==[11,12]:return [dict(id=i,state='confirmed',company_id=1) for i in ids]
            return [dict(id=i,state='confirmed',company_id=1,move_orig_ids=[i-100],move_dest_ids=[i+100]) for i in ids]
        r.b.read=reads
        try:
            with self.assertRaisesRegex(RuntimeError,'Live stage predecessor is not done'):fn(r,[g,g2],grouped=True,month='2026-09',stage_by_so={1:101,2:102})
        finally:fn.__globals__['prepare_root_details_together']=old

if __name__=='__main__':unittest.main()
