"""Read-only Odoo audit; --record-evidence updates the local journal only."""
import argparse
import json
import runpy
from pathlib import Path
BASE=Path(__file__).parent
R=runpy.run_path(str(BASE/'migrate_pysb_independent_receipts.py'))
S=runpy.run_path(str(BASE/'scan_pysb_july_other_stock_coverage.py'))
load=R['load'];save=R['save'];rid=R['rid']
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--record-evidence',action='store_true');args=parser.parse_args()
    if not load('operator-decisions.json')['rounding']['approved']:raise RuntimeError('Operator rounding not approved')
    maps={model:{int(s):t for s,t in values.items()} for model,values in load('after-run-stock-mapping.json')['maps'].items()}
    units={x['id']:x for x in load('target-uom.uom.json')};source={x['id']:x for x in load('source-moves.json')};lines={x['id']:x for x in load('source-move-lines.json')}
    affected=[x for x in lines.values() if maps.get('uom.uom',{}).get(rid(x['product_uom_id'])) and abs(x['qty_done']-R['rounded'](x['qty_done'],units[maps['uom.uom'][rid(x['product_uom_id'])]]['rounding']))>1e-8]
    if len(affected)!=load('quantity-precision-preflight.json')['affected_lines'] or len(affected)!=22:raise RuntimeError('Frozen 22-line approval scope differs')
    allowed={x['id'] for x in affected};journal=load('independent-inventory-journal.json');records=[]
    a=R['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=R['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    for group in journal['groups'].values():
        if group['status']!='verified_done':raise RuntimeError('Incomplete inventory group')
        for evidence in group['before']:
            line=lines[evidence['source_line']];quantity=abs(evidence['delta'])
            if abs(line['qty_done']-quantity)<=1e-8:continue
            if line['id'] not in allowed:raise RuntimeError('Inventory rounding outside frozen approval')
            move=source[evidence['source_move']];unit=maps['uom.uom'][rid(move['product_uom'])]
            if quantity!=R['rounded'](line['qty_done'],units[unit]['rounding']):raise RuntimeError('Prepared count differs from approved rounding')
            if a.read('stock.move',[move['id']],list(move))[0]!=move or a.read('stock.move.line',[line['id']],list(line))[0]!=line:raise RuntimeError('Frozen source changed')
            target=b.read('stock.move',[maps['stock.move'][move['id']]],['state','company_id','date','product_id','product_uom','quantity','location_id','location_dest_id','move_line_ids'])[0]
            target_lines=b.read('stock.move.line',target['move_line_ids'],['state','company_id','date','product_id','product_uom_id','quantity','location_id','location_dest_id','lot_id','owner_id','package_id','result_package_id'])
            adjusted=dict(move,quantity_done=quantity);adjusted_line=dict(line,qty_done=quantity)
            issues=S['verify_move'](adjusted,target,[adjusted_line],target_lines,maps,{}, {})
            if issues or len(target_lines)!=1 or target_lines[0]['date']!=line['date'] or target_lines[0]['state']!='done' or rid(target_lines[0]['company_id'])!=1:raise RuntimeError('Rounded inventory live dimensions/date/company not proven: '+str(issues))
            records.append({'source_line':line['id'],'source_move':move['id'],'source_qty':line['qty_done'],'target_qty':quantity,'target_unit':unit,'delta':quantity-line['qty_done']})
    existing={x['source_line']:x for x in journal['rounding_differences']}
    for record in records:
        if record['source_line'] in existing and existing[record['source_line']]!=record:raise RuntimeError('Conflicting rounding journal evidence')
        if record['source_line'] not in existing:journal['rounding_differences'].append(record)
    save('inventory-approved-rounding-audit.json',{'read_only_odoo':True,'source_approval_lines':len(affected),'verified_rounding_records':records,'journal_recorded':args.record_evidence})
    if args.record_evidence:save('independent-inventory-journal.json',journal)
    print(json.dumps({'approved_inventory_rounding_records':len(records),'local_journal_updated':args.record_evidence}),flush=True)
if __name__=='__main__':main()
