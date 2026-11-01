"""Read-only independent read-back of the exact 13 approved raw demands."""
import json
import runpy
from pathlib import Path
from datetime import datetime, timezone
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
OUT=I['OUT']


def load(name):return json.loads((OUT/name).read_text(encoding='utf8'))


def main():
    approval=load('operator-mo-demand-rounding-approval.json')
    journal=load('independent-mo-journal.json')
    source={x['id']:x for x in load('source-mo-execution-details.json')}
    b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    rows=[]
    for decision in approval['approved_rows']:
        sid=decision['source_mo'];rec=journal['mos'].get(str(sid),{})
        row={'source_mo':sid,'name':decision['name'],'source_move':decision['source_id'],
             'source_demand':decision['source_quantity'],'approved_demand':decision['proposed_target_quantity']}
        rows.append(row)
        if rec.get('status')!='verified_done':
            row['status']='pending_not_completed';continue
        target_id=journal['maps']['stock.move'][str(decision['source_id'])]
        mo=b.read('mrp.production',[rec['target_id']],['state','product_qty','qty_produced','qty_producing','move_raw_ids'])[0]
        move=b.read('stock.move',[target_id],['state','product_uom','product_uom_qty','quantity'])[0]
        original=source[sid]
        checks={'done':mo['state']=='done' and move['state']=='done','raw_owner':target_id in mo['move_raw_ids'],
                'demand':move['product_uom_qty']==decision['proposed_target_quantity'],
                'unit':move['product_uom'][0]==decision['target_unit'],
                'planned_unchanged':mo['product_qty']==original['product_qty'],
                'produced_unchanged':mo['qty_produced']==original['qty_produced'],
                'qty_producing_unchanged':mo['qty_producing']==original['qty_produced']}
        row.update(target_mo=rec['target_id'],target_move=target_id,target_demand=move['product_uom_qty'],
                   delta=move['product_uom_qty']-decision['source_quantity'],checks=checks,
                   status='verified_approved_exception' if all(checks.values()) else 'unresolved',actual_mo=mo,actual_move=move)
    report={'read_only':True,'generated_utc':datetime.now(timezone.utc).isoformat(),'scope':'exact approved 13 raw demands; does not replace detailed stock/MO verification','rows':rows,
            'summary':{status:sum(x['status']==status for x in rows) for status in ['verified_approved_exception','pending_not_completed','unresolved']}}
    I['save']('mo-demand-exception-audit.json',report)
    print(json.dumps(report['summary']),flush=True)
    if report['summary']['unresolved']:raise RuntimeError('Approved demand audit mismatch')


if __name__=='__main__':main()
