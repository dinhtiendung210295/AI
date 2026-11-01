"""Read-only attribution of opening adjustments; no cancellation or stock correction."""
import json,runpy
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def main():
    bad={x['target_id']:x for x in load('native-opening-comparison.json')['rows'] if not x['exact_quantity_match']}
    b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    fields='name origin reference date state company_id product_id product_uom product_uom_qty quantity location_id location_dest_id picking_id move_line_ids is_inventory inventory_name description_picking_manual'.split()
    moves=b.scan('stock.move',[['company_id','=',1],['state','=','done'],['date','<',load('scope.json')['start_utc']],['product_id','in',list(bad)],['is_inventory','=',True]],fields)
    external=b.scan('ir.model.data',[['model','=','stock.move'],['res_id','in',[x['id'] for x in moves]]],['module','name','res_id','model'])
    ids=defaultdict(list)
    for row in external:ids[row['res_id']].append(row)
    lines=b.read('stock.move.line',[i for x in moves for i in x['move_line_ids']],['move_id','product_id','product_uom_id','quantity','lot_id','location_id','location_dest_id','package_id','result_package_id','owner_id','date'])
    bymove=defaultdict(list)
    for line in lines:bymove[rid(line['move_id'])].append(line)
    results=[]
    for move in moves:
        description=' '.join(str(move.get(k) or '') for k in ['name','origin','reference','inventory_name','description_picking_manual'])
        tagged=('TEMP' in description.upper()) or any('tempor' in x['module'].lower() for x in ids[move['id']])
        results.append(dict(move=move,external_ids=ids[move['id']],lines=bymove[move['id']],temporary_tag_candidate=tagged,opening_difference=bad[rid(move['product_id'])]))
    report=dict(read_only=True,write_authorized=False,generated_utc=datetime.now(timezone.utc).isoformat(),scope='Existing target inventory moves before August opening, for 45 mapped products with differing opening quantities',rows=results,summary=dict(inventory_moves=len(moves),temporary_tag_candidates=sum(x['temporary_tag_candidate'] for x in results),external_modules=dict(Counter(x['module'] for x in external))),note='Tags alone are not approval or proof of a remaining temporary balance. Preserve validated history; reconcile with source and target ledger before proposing corrections.')
    I['save']('opening-adjustment-provenance.json',report);print(json.dumps(report['summary']),flush=True)
    print(json.dumps([dict(target_move=x['move']['id'],product=x['move']['product_id'],date=x['move']['date'],quantity=x['move']['quantity'],origin=x['move'].get('origin')) for x in results if x['temporary_tag_candidate']][:8],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
