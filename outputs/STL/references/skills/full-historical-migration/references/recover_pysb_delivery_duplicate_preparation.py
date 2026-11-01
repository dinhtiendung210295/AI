"""Explicit read-back recovery of a job-created, unconsumed duplicate; no retry."""
import argparse,json,runpy
from pathlib import Path
from collections import defaultdict
BASE=Path(__file__).parent
M=runpy.run_path(str(BASE/'migrate_pysb_independent_deliveries.py'))
G=runpy.run_path(str(BASE/'delivery_preparation_cleanup_guard.py'))
rid=M['rid']
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    r=M['Run']();lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](M['OUT'])
    sid=63698;source_mid=513079;original_id=20403;extra_id=20408
    rec=r.j['groups'][str(sid)]
    if rec.get('duplicate_preparation_cleanup'):
        if rec['duplicate_preparation_cleanup']['status']=='verified_removed':print('already_removed');return
        raise RuntimeError('Interrupted cleanup requires explicit read-back; do not repeat')
    if r.uncertain or rec['phase']!='order_confirmed':raise RuntimeError('Unexpected interrupted phase')
    row=next(x for x in r.planrows if x['source_so']==sid);group=r.group(row);source=r.sm[source_mid]
    if group['target'].get('picking_ids'):raise RuntimeError('Existing pre-migration pickings must not be cleaned')
    if r.a.read('stock.move',[source_mid],list(source))[0]!=source:raise RuntimeError('Source physical fact changed')
    source_same=[x for x in (r.sm[i] for i in group['moves']) if all(rid(x[f])==rid(source[f]) for f in ['product_id','product_uom','location_id','location_dest_id'])]
    if len(source_same)!=1 or source_same[0]['id']!=source_mid or source['move_orig_ids']:raise RuntimeError('Source has another needed physical leg')
    fields='state company_id product_id product_uom product_uom_qty quantity picked location_id location_dest_id move_line_ids move_orig_ids move_dest_ids origin_returned_move_id returned_move_ids production_id raw_material_production_id created_production_id purchase_line_id sale_line_id bom_line_id create_uid create_date rule_id origin picking_id'.split()
    native=r.b.read('stock.move',[original_id,extra_id],fields);original=next(x for x in native if x['id']==original_id);extra=next(x for x in native if x['id']==extra_id)
    operations=[x for x in r.j['operations'] if x['model']=='stock.move' and x['method']=='create' and x.get('result')==extra_id]
    if len(operations)!=1:raise RuntimeError('Creation provenance not unique')
    product=r.maps['product.product'][rid(source['product_id'])];unit=r.maps['uom.uom'][rid(source['product_uom'])];line=rid(original['sale_line_id'])
    live_line=r.b.read('sale.order.line',[line],['order_id','product_id','product_uom_id','product_uom_qty','qty_delivered'])[0]
    if rid(live_line['order_id'])!=rec['target_order'] or rid(live_line['product_id'])!=product or rid(live_line['product_uom_id'])!=unit or live_line['product_uom_qty']!=original['product_uom_qty'] or live_line['qty_delivered']:raise RuntimeError('Commercial line no longer unchanged/unconsumed')
    if rid(original['location_id'])!=r.maps['stock.location'][rid(source['location_id'])] or rid(original['location_dest_id'])!=r.maps['stock.location'][rid(source['location_dest_id'])]:raise RuntimeError('Original native leg is not the source physical leg')
    G['check'](extra,original,source,operations[0],product,unit,line,1,r.b.r.uid)
    if r.b.scan('ir.model.data',[['model','=','stock.move'],['res_id','=',extra_id]],['name']):raise RuntimeError('Created duplicate has an external identity')
    def stock():
        rows=r.b.scan('stock.quant',[['company_id','=',1],['product_id','=',product]],['product_id','location_id','lot_id','package_id','owner_id','quantity','reserved_quantity'])
        totals=defaultdict(lambda:[0.,0.])
        for x in rows:
            key=tuple(rid(x[f]) for f in ['product_id','location_id','lot_id','package_id','owner_id']);totals[key][0]+=x['quantity'];totals[key][1]+=x['reserved_quantity']
        return {str(key):value for key,value in totals.items() if any(abs(v)>1e-8 for v in value)}
    proof={'status':'validated_not_executed','source_so':sid,'source_move':source,'original_native':original,'created_duplicate':extra,'creation_operation':operations[0],'stock_before':stock()}
    M['save']('delivery-63698-duplicate-cleanup-proof.json',proof)
    if not args.execute:print(json.dumps({'safe_to_remove_own_duplicate':extra_id,'source_pick_demand':source['product_uom_qty'],'original_native_demand':original['product_uom_qty'],'stock_quantity_changed':False}));return
    proof['status']='intent';rec['duplicate_preparation_cleanup']=proof;r.persist()
    r.mutate('stock.move','unlink',[[extra_id]])
    if r.b.scan('stock.move',[['id','=',extra_id]],['state']):raise RuntimeError('Duplicate still exists after unlink')
    after=stock()
    if after!=proof['stock_before']:raise RuntimeError('Physical stock/reservation changed during cleanup; read back')
    proof.update(status='verified_removed',stock_after=after);r.persist();M['save']('delivery-63698-duplicate-cleanup-proof.json',proof)
    print(json.dumps({'removed_own_unconsumed_duplicate':extra_id,'stock_quantity_changed':False}),flush=True)
if __name__=='__main__':main()
