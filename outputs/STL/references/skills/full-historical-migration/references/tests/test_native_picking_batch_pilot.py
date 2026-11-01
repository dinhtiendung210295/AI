import runpy,unittest
from types import SimpleNamespace
from pathlib import Path
M=runpy.run_path(str(Path(__file__).parents[1]/'native_picking_batch_pilot.py'))
class Tests(unittest.TestCase):
    def fixture(self):
        rows=[dict(source_so=1,roots=[1],moves=[1,3]),dict(source_so=2,roots=[2],moves=[2,4])]
        moves={1:dict(picking_id=[11,'P'],move_orig_ids=[],move_dest_ids=[3]),2:dict(picking_id=[12,'P'],move_orig_ids=[],move_dest_ids=[4]),3:dict(picking_id=[13,'P'],move_orig_ids=[1],move_dest_ids=[]),4:dict(picking_id=[14,'P'],move_orig_ids=[2],move_dest_ids=[])}
        picks={i:dict(date_done='2026-08-01 01:00:00',picking_type_id=[1,'Pick']) for i in [11,12,13,14]}
        return rows,moves,picks
    def test_independent_same_day_same_type(self):
        rows,moves,picks=self.fixture();self.assertEqual(len(M['select'](rows,moves,picks)),2)
    def test_ten_selection_requires_pairwise_independence(self):
        rows=[dict(source_so=i,roots=[i],moves=[i]) for i in range(1,11)]
        moves={i:dict(picking_id=[i,'P'],move_orig_ids=[],move_dest_ids=[]) for i in range(1,11)}
        picks={i:dict(date_done='2026-09-01 01:00:00',picking_type_id=[1,'Pick']) for i in range(1,11)}
        self.assertEqual(len(M['select_ten'](rows,moves,picks)),10)
        moves[1]['move_dest_ids']=[10]
        with self.assertRaises(RuntimeError):M['select_ten'](rows,moves,picks)
    def test_cross_dependency_other_day_other_type_rejected(self):
        for case in ['dependency','day','type']:
            rows,moves,picks=self.fixture()
            if case=='dependency':moves[1]['move_dest_ids'].append(2)
            if case=='day':picks[12]['date_done']='2026-08-02 01:00:00'
            if case=='type':picks[12]['picking_type_id']=[2,'Delivery']
            with self.assertRaises(RuntimeError):M['select'](rows,moves,picks)
    def test_pair_scheduler_keeps_event_order_and_finishes_dependent_stages_singly(self):
        rows,moves,picks=self.fixture();picks[13]['date_done']='2026-08-01 02:00:00';picks[14]['date_done']='2026-08-01 03:00:00'
        groups=[dict(source={'id':row['source_so']},moves=row['moves'],pickings=[11,13] if row['source_so']==1 else [12,14]) for row in rows]
        records={'1':{'completed_pickings':[]},'2':{'completed_pickings':[]}};calls=[]
        def finish(g,only_picking):records[str(g['source']['id'])]['completed_pickings'].append(only_picking);calls.append(('single',only_picking))
        r=SimpleNamespace(sm=moves,sp=picks,j={'groups':records},finish=finish)
        fn=M['finish_events_in_pairs'];previous=fn.__globals__['validate']
        def validate(reader,selected):
            calls.append(('pair',11,12));records['1']['completed_pickings'].append(11);records['2']['completed_pickings'].append(12);return {}
        fn.__globals__['validate']=validate
        try:self.assertEqual(fn(r,groups),1)
        finally:fn.__globals__['validate']=previous
        self.assertEqual(calls,[('pair',11,12),('single',13),('single',14)])
if __name__=='__main__':unittest.main()
