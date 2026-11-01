"""Read-only evidence outside frozen scope: July 31 flows explaining August opening gaps."""
import json,runpy
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def main():
    bad={x['source_id']:x for x in load('native-opening-comparison.json')['rows'] if not x['exact_quantity_match']}
    a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    fields='name date state company_id product_id product_uom product_uom_qty quantity_done location_id location_dest_id picking_id move_line_ids production_id raw_material_production_id inventory_id origin_returned_move_id purchase_line_id sale_line_id write_date'.split()
    source=a.scan('stock.move',[['company_id','=',1],['state','=','done'],['date','>=','2026-07-30 16:00:00'],['date','<','2026-07-31 16:00:00'],['product_id','in',list(bad)]],fields)
    lines=a.read('stock.move.line',[i for x in source for i in x['move_line_ids']],['move_id','product_id','product_uom_id','qty_done','lot_id','location_id','location_dest_id','package_id','result_package_id','owner_id','date'])
    by_move=defaultdict(list)
    for line in lines:by_move[rid(line['move_id'])].append(line)
    maps=load('after-run-stock-mapping.json')['maps'];locations={x['id']:x for x in load('source-stock.location.json')};units={x['id']:x for x in load('source-uom.uom.json')};products={x['id']:x for x in load('source-products.json')}
    # Existing maps are identities only: always read live completion and quantities.
    mids={x['id']:maps.get('stock.move',{}).get(str(x['id'])) for x in source}
    targets={x['id']:x for x in b.read('stock.move',[x for x in mids.values() if x],['state','company_id','product_id','date','quantity','product_uom','product_uom_qty','location_id','location_dest_id','move_line_ids'])}
    results=[];missing_net=defaultdict(float);last_hour_net=defaultdict(float)
    for move in source:
        pid=rid(move['product_id']);signed=0.
        for line in by_move[move['id']]:
            qty=line['qty_done']*units[rid(products[pid]['uom_id'])]['factor']/units[rid(line['product_uom_id'])]['factor']
            signed+=qty*((locations[rid(line['location_dest_id'])]['usage']=='internal')-(locations[rid(line['location_id'])]['usage']=='internal'))
        target=targets.get(mids[move['id']]);status='mapped_done_requires_detailed_audit' if target and target['state']=='done' else 'target_not_done' if target else 'unmapped_source_move'
        if status!='mapped_done_requires_detailed_audit':
            missing_net[pid]+=signed
            if move['date']>='2026-07-31 15:00:00':last_hour_net[pid]+=signed
        results.append(dict(source_move=move,target=target,completion_status=status,signed_source_internal_quantity=signed,source_lines=by_move[move['id']]))
    findings=[]
    for pid,row in bad.items():
        findings.append(dict(**row,july31_not_done_net=missing_net[pid],last_hour_not_done_net=last_hour_net[pid],delta_after_missing_flow_replay=row['delta']+missing_net[pid],explained_by_missing_july31_flows=abs(row['delta']+missing_net[pid])<=1e-6 and abs(missing_net[pid])>1e-6))
    report=dict(discovery_only=True,outside_frozen_scope=True,write_authorized=False,generated_utc=datetime.now(timezone.utc).isoformat(),source_window_utc=['2026-07-30 16:00:00','2026-07-31 16:00:00'],rows=results,products=findings,summary=dict(source_moves=len(source),statuses=dict(Counter(x['completion_status'] for x in results)),products_explained=sum(x['explained_by_missing_july31_flows'] for x in findings)),note='Evidence only; mapped done is not detailed verification. Requires review and explicit scope approval before replaying any July transaction.')
    I['save']('july31-opening-dependency-review.json',report);print(json.dumps(report['summary']),flush=True)
    print(json.dumps([dict(name=x['name'],opening_delta=x['delta'],missing_source_net=x['july31_not_done_net']) for x in findings if x['explained_by_missing_july31_flows']][:8],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
