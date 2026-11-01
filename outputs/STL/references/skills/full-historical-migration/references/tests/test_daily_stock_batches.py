import runpy,unittest
from types import SimpleNamespace
from pathlib import Path
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'native_picking_batch_pilot.py'))

class DailySelectionTest(unittest.TestCase):
    def test_malaysia_midnight(self):
        self.assertEqual(M['local_day']('2026-09-01 15:59:59'),'2026-09-01')
        self.assertEqual(M['local_day']('2026-09-01 16:00:00'),'2026-09-02')

    def test_select_whole_earliest_local_day_without_count_limit(self):
        rows=[{'pickings':[i]} for i in range(1,103)]
        picks={i:{'date_done':'2026-09-01 17:00:00' if i%2 else '2026-09-02 01:00:00'} for i in range(1,103)}
        rows.insert(0,{'pickings':[103]});picks[103]={'date_done':'2026-09-03 01:00:00'}
        day,chosen=M['select_day'](rows,picks)
        self.assertEqual(day,'2026-09-02');self.assertEqual(len(chosen),102)

    def test_cross_day_chain_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'Cross-day'):
            M['select_day']([{'pickings':[1,2]}],{1:{'date_done':'2026-09-01 15:59:59'},2:{'date_done':'2026-09-01 16:00:00'}})

    def test_empty(self):self.assertEqual(M['select_day']([],{}),(None,[]))

    def test_daily_batches_all_roots_once_then_skips_completed_roots(self):
        groups=[dict(source={'id':i},moves=[i,i+100],pickings=[i,i+100]) for i in range(1,13)]
        moves={};picks={};records={};calls=[]
        for i in range(1,13):
            moves[i]=dict(picking_id=i,move_orig_ids=[],move_dest_ids=[i+100])
            moves[i+100]=dict(picking_id=i+100,move_orig_ids=[i],move_dest_ids=[])
            picks[i]=dict(date_done='2026-09-02 01:00:00',picking_type_id=1)
            picks[i+100]=dict(date_done='2026-09-02 02:00:00',picking_type_id=2)
            records[str(i)]={'completed_pickings':[]}
        def finish(g,only_picking):
            records[str(g['source']['id'])]['completed_pickings'].append(only_picking);calls.append(('single',only_picking))
        r=SimpleNamespace(sm=moves,sp=picks,j={'groups':records},finish=finish,persist=lambda:None)
        fn=M['finish_daily'];previous=fn.__globals__['validate']
        def validate(reader,selected,grouped=False,day_mode=False):
            self.assertTrue(grouped and day_mode);self.assertEqual(len(selected),12)
            calls.append(('batch',12))
            for g in selected:records[str(g['source']['id'])]['completed_pickings'].append(g['source']['id'])
            return {}
        fn.__globals__['validate']=validate
        try:self.assertEqual(fn(r,groups,'2026-09-02'),1)
        finally:fn.__globals__['validate']=previous
        self.assertEqual(calls,[('batch',12)]+[('single',i) for i in range(101,113)])

if __name__=='__main__':unittest.main()
