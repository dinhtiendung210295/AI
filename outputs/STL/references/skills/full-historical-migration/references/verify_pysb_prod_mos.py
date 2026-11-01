"""Read-only live MO audit against the frozen source snapshot."""
import argparse
import json
import runpy
import socket
import sys
from collections import defaultdict
from pathlib import Path

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from mo_quantity_checks import compare_mos
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
S=runpy.run_path(str(BASE/'scan_pysb_july_other_stock_coverage.py'))

def run(evidence):
    socket.setdefaulttimeout(120)
    def load(n):return json.loads((evidence/n).read_text(encoding='utf8'))
    d=load('discovery-manifest.json')
    maps={m:{int(s):t for s,t in pairs.items()} for m,pairs in d['maps'].items()}
    if (evidence/'after-run-stock-mapping.json').exists():
        maps={m:{int(s):t for s,t in pairs.items()} for m,pairs in load('after-run-stock-mapping.json')['maps'].items()}
        for name in ['independent-mo-journal.json','independent-receipts-journal.json']:
            if not (evidence/name).exists():continue
            for model,pairs in load(name)['maps'].items():
                if any(maps.get(model,{}).get(int(s))!=t for s,t in pairs.items()):raise RuntimeError('After-run mapping stale; refresh coverage before MO verification')
    b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    source=load('source-mos.json')
    target=b.read('mrp.production',[maps.get('mrp.production',{}).get(s['id']) for s in source], 'name state company_id date_start date_finished product_id product_uom_id product_qty qty_produced move_raw_ids move_finished_ids'.split())
    target_moves=b.read('stock.move',[i for x in target for k in ['move_raw_ids','move_finished_ids'] for i in x[k]], S['MOVE_FIELDS'])
    target_lines=b.read('stock.move.line',[i for x in target_moves for i in x['move_line_ids']], S['LINE_FIELDS'])
    source_moves=load('source-moves.json')+load('source-document-extra-moves.json')
    sl,tl=defaultdict(list),defaultdict(list)
    for x in load('source-move-lines.json'):sl[S['rid'](x['move_id'])].append(x)
    for x in target_lines:tl[S['rid'](x['move_id'])].append(x)
    ti={x['id']:x for x in target_moves}
    conflicts={(x['model'],x['source_id']):x['targets'] for x in d['mapping_conflicts']}
    coverage={};expected_exceptions={};rounding_records={}
    for name in ['independent-mo-journal.json','independent-receipts-journal.json','independent-delivery-journal.json']:
        if not (evidence/name).exists():continue
        for record in load(name).get('rounding_differences',[]):
            sid=record.get('source_line',record.get('source_line_id'))
            if sid is None:raise RuntimeError('Rounding record missing source line')
            if sid in rounding_records and rounding_records[sid]!=record:raise RuntimeError('Conflicting rounding record')
            rounding_records[sid]=record
    source_units={x['id']:x for x in load('source-uom.uom.json')}
    target_units={x['id']:x for x in load('target-uom.uom.json')}
    adjusted_source=runpy.run_path(str(BASE/'approved_stock_rounding.py'))['adjusted_source']
    approval=load('operator-mo-demand-rounding-approval.json') if (evidence/'operator-mo-demand-rounding-approval.json').exists() else {}
    demand_check=runpy.run_path(str(BASE/'approved_mo_demand_rounding.py'))['demand_quantity']
    owner={mid:s for s in source for mid in s['move_raw_ids']+s['move_finished_ids']}
    for move in source_moves:
        tid=maps.get('stock.move',{}).get(move['id'])
        if tid in ti:
            coverage[move['id']]='verified' if not S['verify_move'](move,ti[tid],sl[move['id']],tl[tid],maps,conflicts,{}) else 'unresolved'
            if any(x['id'] in rounding_records for x in sl[move['id']]):
                adjusted,adjusted_lines,differences=adjusted_source(move,sl[move['id']],rounding_records,maps,source_units,target_units)
                if not S['verify_move'](adjusted,ti[tid],adjusted_lines,tl[tid],maps,conflicts,{}):
                    coverage[move['id']]='approved_exception'
                    expected_exceptions.setdefault(move['id'],{})['done']={'source':move['quantity_done'],'target':adjusted['quantity_done'],'proof':'approved_stock_detail_rounding','differences':differences}
            if move['id'] in owner and any(x['source_id']==move['id'] for x in approval.get('approved_rows',[])):
                unit=maps['uom.uom'].get(S['rid'](move['product_uom']))
                value,record=demand_check(owner[move['id']],move,unit,target_units[unit]['rounding'],approval)
                if record:expected_exceptions.setdefault(move['id'],{})['demand']={'source':move['product_uom_qty'],'target':value,'proof':'operator_approved_13_raw_demands','difference':record}
    units={x['id']:x for x in load('source-uom.uom.json')}
    report=compare_mos(source,target,source_moves,target_moves,maps,units,coverage)
    report=runpy.run_path(str(BASE/'mo_approved_exception_checks.py'))['annotate'](report,coverage,expected_exceptions)
    report['scope']=load('scope.json');report['database']=b.r.db
    (evidence/'mo-quantity-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report['summary']),flush=True)
    return 1 if report['summary']['mismatched'] else 0

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence-dir',type=Path,required=True)
    raise SystemExit(run(p.parse_args().evidence_dir))
