"""Offline behavioral regressions for the existing DO/MO coverage scripts."""
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import importlib
from pathlib import Path

REF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REF))
import scan_pysb_july_other_stock_coverage as C
from discover_pysb_supporting_stock import discover


class Fake:
    def __init__(self, data): self.data=data;self.calls=[]
    def call(self, model, method, args, kw):
        self.calls.append((model,method))
        if method=='fields_get':
            return {k:{} for r in self.data.get(model,[]) for k in r}
        rows=copy.deepcopy(self.data.get(model,[]))
        if method=='read':
            return [r for r in rows if r['id'] in args[0]]
        if method not in {'search_count','search_read'}:raise AssertionError('write called')
        for field,op,value in args[0]:
            def ok(r):
                v=C.rid(r.get(field)) if field.endswith('_id') else r.get(field)
                return {'=':lambda:v==value,'>':lambda:v>value,'>=':lambda:v>=value,
                        '<':lambda:v<value,'in':lambda:v in value}[op]()
            rows=[r for r in rows if ok(r)]
        if method=='search_count':return len(rows)
        return sorted(rows,key=lambda r:r['id'])[:kw['limit']]


def fixture():
    source={'id':10,'name':'arbitrary','date':C.START,'state':'done','company_id':[1,'PYSB'],
            'product_id':[2,'P'],'product_uom':[3,'UNIT'],'product_uom_qty':1,
            'quantity_done':1,'location_id':[4,'Stock'],'location_dest_id':[5,'Customer'],
            'picking_id':[6,'arbitrary'],'move_line_ids':[7], 'move_orig_ids':[],
            'move_dest_ids':[], 'inventory_id':False, 'scrapped':False,
            'production_id':False,'raw_material_production_id':False}
    line={'id':7,'move_id':[10,'M'],'product_id':[2,'P'],'product_uom_id':[3,'UNIT'],
          'qty_done':1,'location_id':[4,'Stock'],'location_dest_id':[5,'Customer'],
          'lot_id':False,'package_id':False,'result_package_id':False,'owner_id':False}
    target=copy.deepcopy(source);target.update(id=110,move_line_ids=[107],quantity=1)
    tl=copy.deepcopy(line);tl.update(id=107,move_id=[110,'M'],quantity=1)
    maps={'stock.move':{'10':110},'product.product':{'2':2},'uom.uom':{'3':3},'stock.location':{'4':4,'5':5}}
    pick={'id':6,'name':'not-RTN-or-CON-or-INT','origin':'SO-from-June','date_done':C.START,
          'state':'done','company_id':[1,'PYSB'],'move_lines':[10]}
    locs=[{'id':4,'usage':'internal'},{'id':5,'usage':'customer'}]
    a=Fake({'stock.move':[source],'stock.move.line':[line],'stock.picking':[pick],'stock.location':locs})
    b=Fake({'stock.move':[target],'stock.move.line':[tl]})
    return a,b,{'maps':maps},{}


class CoverageTests(unittest.TestCase):
    def runscan(self,a,b,m,j):return C.scan(C.ReadOnly(a),C.ReadOnly(b),m,j)
    def test_verified_requires_live_details(self):
        r=self.runscan(*fixture());self.assertEqual(r['results'][0]['status'],'verified')
        self.assertTrue(r['full_acceptance_ready'])
    def test_old_so_arbitrary_names_retained(self):
        a,b,m,j=fixture();m['maps']['stock.move']={};r=self.runscan(a,b,m,j)
        self.assertEqual(r['pending_pickings'][0]['unknown_moves'],[10])
    def test_unmapped_product_not_filtered(self):
        a,b,m,j=fixture();m['maps'].pop('product.product');r=self.runscan(a,b,m,j)
        self.assertEqual(len(r['source_moves']),1);self.assertEqual(r['results'][0]['status'],'unresolved')
    def test_scrap_without_inventory_or_picking(self):
        a,b,m,j=fixture();s=a.data['stock.move'][0];s.update(picking_id=False,scrapped=True)
        m['maps']['stock.move']={};r=self.runscan(a,b,m,j)
        self.assertEqual(r['results'][0]['category'],'scrap');self.assertEqual(len(r['pending_moves']),1)
    def test_mo_and_unbuild_categories(self):
        for field,label in [('production_id','mo_finished'),('raw_material_production_id','mo_raw'),('unbuild_id','unbuild')]:
            with self.subTest(field=field):
                a,b,m,j=fixture();a.data['stock.move'][0][field]=[20,'MO'];r=self.runscan(a,b,m,j)
                self.assertEqual(r['results'][0]['category'],label)
    def test_missing_draft_cancelled_targets(self):
        for state in [None,'draft','cancel']:
            with self.subTest(state=state):
                a,b,m,j=fixture()
                if state is None:b.data['stock.move']=[]
                else:b.data['stock.move'][0]['state']=state
                self.assertEqual(self.runscan(a,b,m,j)['results'][0]['status'],'unresolved')
    def test_wrong_quantity_and_date(self):
        for field,value in [('quantity',2),('date',C.END)]:
            a,b,m,j=fixture();b.data['stock.move'][0][field]=value
            self.assertEqual(self.runscan(a,b,m,j)['results'][0]['status'],'unresolved')
    def test_wrong_lot_and_location(self):
        for field,value in [('lot_id',[99,'Wrong']),('location_id',[99,'Wrong'])]:
            a,b,m,j=fixture();b.data['stock.move.line'][0][field]=value
            self.assertEqual(self.runscan(a,b,m,j)['results'][0]['status'],'unresolved')
    def test_known_scrap_not_replayed(self):
        a,b,m,j=fixture()
        for r in [a.data['stock.move'][0],b.data['stock.move'][0]]:r['scrapped']=True;r['picking_id']=False
        self.assertFalse(self.runscan(a,b,m,j)['pending_moves'])
    def test_rounding_remains_exception(self):
        a,b,m,j=fixture();a.data['stock.move'][0]['quantity_done']=0.972
        a.data['stock.move.line'][0]['qty_done']=0.972;b.data['stock.move'][0]['quantity']=0.97;b.data['stock.move.line'][0]['quantity']=0.97
        j['precision_differences']={'10':{'target_move':110,'source_qty':0.972,'target_qty':0.97}}
        r=self.runscan(a,b,m,j);self.assertEqual(r['results'][0]['status'],'approved_exception');self.assertFalse(r['full_acceptance_ready'])
    def test_conflicting_mapping(self):
        a,b,m,j=fixture();j={'maps':{'stock.move':{'10':111}}}
        self.assertIn('conflicting_move_mapping',self.runscan(a,b,m,j)['results'][0]['issues'])
    def test_unknown_retained(self):
        a,b,m,j=fixture();a.data['stock.location'][0]['usage']='view'
        self.assertIn('unclassified_source_move',self.runscan(a,b,m,j)['results'][0]['issues'])
    def test_period_and_company_boundaries(self):
        a,b,m,j=fixture();s=a.data['stock.move'][0]
        a.data['stock.move'] += [dict(s,id=11,date=C.END),dict(s,id=12,date='2026-06-30 15:59:59'),dict(s,id=13,company_id=[2,'Other']),dict(s,id=14,state='draft')]
        self.assertEqual([x['id'] for x in self.runscan(a,b,m,j)['source_moves']],[10])
    def test_page_cursor_handles_server_cap(self):
        a,b,m,j=fixture();base=a.data['stock.move'][0];a.data['stock.move']=[dict(base,id=i) for i in range(1,13)]
        rows=C.paged(C.ReadOnly(a),'stock.move',[],['id'],page_size=3)
        self.assertEqual([x['id'] for x in rows],list(range(1,13)))
    def test_count_mismatch_raises(self):
        a,b,m,j=fixture();orig=a.call
        a.call=lambda model,method,args,kw:99 if method=='search_count' else orig(model,method,args,kw)
        with self.assertRaises(RuntimeError):C.paged(C.ReadOnly(a),'stock.move',[],['id'])
    def test_repeating_page_raises(self):
        a,b,m,j=fixture();orig=a.call
        a.call=lambda model,method,args,kw:copy.deepcopy(a.data[model]) if method=='search_read' else orig(model,method,args,kw)
        with self.assertRaises(RuntimeError):C.paged(C.ReadOnly(a),'stock.move',[],['id'])
    def test_api_failure_never_passes(self):
        a,b,m,j=fixture();a.call=lambda *args:(_ for _ in ()).throw(OSError('offline'))
        with self.assertRaises(OSError):self.runscan(a,b,m,j)
    def test_write_denied(self):
        a,*_=fixture()
        with self.assertRaises(RuntimeError):C.ReadOnly(a).call('stock.move','create',[{}])
    def test_discover_complete_picking_and_outside_dependency(self):
        a,b,m,j=fixture();m['maps']['stock.move']={};s=a.data['stock.move'][0]
        other=dict(s,id=11,date=C.END,picking_id=False,move_line_ids=[])
        a.data['stock.move'].append(other);a.data['stock.picking'][0]['move_lines'].append(11)
        report=self.runscan(a,b,m,j);details=discover(C.ReadOnly(a),report,{})
        self.assertEqual({x['id'] for x in details['all_moves']},{10,11})
        self.assertIn(11,details['out_of_period_or_not_done_move_ids']);self.assertFalse(details['execution_authorized'])
    def test_discover_mo_keeps_both_sides(self):
        a,b,m,j=fixture();m['maps']['stock.move']={};s=a.data['stock.move'][0]
        s.update(production_id=[20,'MO'],picking_id=False)
        a.data['mrp.production']=[{'id':20,'name':'MO','company_id':[1,'PYSB'],'move_raw_ids':[11],'move_finished_ids':[10]}]
        a.data['stock.move'].append(dict(s,id=11,production_id=False,raw_material_production_id=[20,'MO'],move_line_ids=[]))
        details=discover(C.ReadOnly(a),self.runscan(a,b,m,j),{})
        self.assertEqual({x['id'] for x in details['mo_moves']},{10,11})
    def test_real_twenty_missed_moves(self):
        path=C.ROOT/'outputs/pysb-sue-stock-review-20261020/source-creation-dates.json'
        if not path.exists():self.skipTest('Historical evidence not installed')
        evidence=json.loads(path.read_text(encoding='utf8'));a,b,m,j=fixture();base=a.data['stock.move'][0]
        a.data['stock.move']=[dict(base,**r,move_line_ids=[]) for r in evidence['moves']]
        # copy dates/IDs/order relationships from real source, add only the
        # stock fields that the creation-date evidence did not request.
        a.data['stock.picking']=[dict(a.data['stock.picking'][0],**p,move_lines=[r['id'] for r in evidence['moves'] if C.rid(r['picking_id'])==p['id']]) for p in evidence['pickings']]
        for r in a.data['stock.move']:
            r['scrapped']=r['name'].startswith('SP/');r['location_dest_id']=[5,'Customer']
        m['maps']['stock.move']={};r=self.runscan(a,b,m,j)
        self.assertEqual(len(r['pending_moves']),20)
        self.assertEqual(sum(x['category']=='scrap' for x in r['results']),17)
        self.assertEqual(len(r['pending_pickings']),3)
    def test_acceptance_gate_rejects_missing_old_failed_or_unresolved(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'r.json';self.assertFalse(C.acceptance_gate(p)['full_acceptance_ready'])
            for data in [{},{'schema_version':2,'scan_complete':False},self.runscan(*fixture())]:
                if 'results' in data:data['results'][0]['status']='unresolved'
                p.write_text(json.dumps(data),encoding='utf8');self.assertFalse(C.acceptance_gate(p)['full_acceptance_ready'])
    def test_acceptance_requires_source_and_result_sets_and_counts(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'r.json';data=self.runscan(*fixture());p.write_text(json.dumps(data),encoding='utf8')
            self.assertTrue(C.acceptance_gate(p)['full_acceptance_ready'])
            data['source_moves']=[];p.write_text(json.dumps(data),encoding='utf8')
            self.assertFalse(C.acceptance_gate(p)['full_acceptance_ready'])
    def test_legacy_writers_refuse_discovery_before_writes(self):
        for name,constructor in [('prepare_pysb_supporting_transfers','Migration'),
                                 ('apply_pysb_supporting_adjustments','Completion'),
                                 ('batch_pysb_supporting_inventory_adjustments','Completion')]:
            with self.subTest(name=name):
                module=importlib.import_module(name)
                with patch.object(module,constructor,return_value=SimpleNamespace()),patch.object(module,'load',return_value={'discovery_only':True}):
                    with self.assertRaisesRegex(RuntimeError,'Discovery-only coverage'):module.main()
    def test_failed_rerun_invalidates_previous_report(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);C.save(p/'july-other-stock-coverage.json',self.runscan(*fixture()))
            with patch.object(C,'readers',side_effect=OSError('offline')):
                with self.assertRaises(OSError):C.run_scan(p/'evidence',p)
            self.assertFalse(C.acceptance_gate(p/'july-other-stock-coverage.json')['full_acceptance_ready'])
    def test_historical_output_never_written_even_with_other_evidence_path(self):
        with patch.object(C,'save') as save:
            with self.assertRaises(RuntimeError):C.run_scan(Path('other-evidence'),C.EVIDENCE)
            save.assert_not_called()


if __name__=='__main__':unittest.main()
