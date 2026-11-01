"""Offline August Scrap/Unbuild dependency and supply review; never executes ERP."""
import json,runpy
from pathlib import Path
from collections import defaultdict,Counter
from decimal import Decimal,ROUND_HALF_UP
BASE=Path(__file__).parent;I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def main():
    moves=load('source-moves.json');cov={x['source_move_id']:x for x in load('after-run-stock-coverage.json')['results']};maps=load('after-run-stock-mapping.json')['maps'];loc={x['id']:x for x in load('source-stock.location.json')};products={x['id']:x for x in load('source-products.json')};units={x['id']:x for x in load('source-uom.uom.json')};tu={x['id']:x for x in load('target-uom.uom.json')};lines=defaultdict(list)
    for x in load('source-move-lines.json'):lines[rid(x['move_id'])].append(x)
    held={x['source_id'] for x in load('native-opening-comparison.json')['rows'] if not x['exact_quantity_match']};held.update(x['source_id'] for x in load('resolved-master-evidence.json')['issues'] if x['model']=='product.product')
    valid={tuple(x['target_key']) for x in load('detailed-opening-comparison.json')['rows'] if x['exact_match']};pool=defaultdict(float)
    def mapped(model,sid):return maps.get(model,{}).get(str(sid),maps.get(model,{}).get(sid)) if sid else False
    for row in load('source-detailed-opening-reconstruction.json')['rows']:
        target=tuple(mapped(m,s) for m,s in zip(['product.product','stock.location','stock.lot','stock.package','res.partner'],row['key']))
        if target in valid:pool[tuple(row['key'])]=row['quantity']
    def key(x,origin=True):return (rid(x['product_id']),rid(x['location_id'] if origin else x['location_dest_id']),rid(x['lot_id']),rid(x['package_id'] if origin else x['result_package_id']),rid(x['owner_id']))
    def qty(x,consume=False):
        u=rid(x['product_uom_id']);target=mapped('uom.uom',u);q=x['qty_done']
        if target:
            precision=Decimal(str(tu[target]['rounding']));rounded=float((Decimal(str(q))/precision).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*precision);q=max(q,rounded) if consume else rounded
        return q*units[rid(products[rid(x['product_id'])]['uom_id'])]['factor']/units[u]['factor']
    rows=[]
    for m in sorted(moves,key=lambda x:(x['date'],x['id'])):
        mid=m['id'];c=cov[mid];details=lines[mid];in_august='2026-07-31 16:00:00'<=m['date']<'2026-08-31 16:00:00'
        if in_august and c['status']=='unresolved' and c['category'] in ['scrap','unbuild']:
            errors=[];needs=defaultdict(float)
            if rid(m['product_id']) in held:errors.append('product_opening_or_master_hold')
            if c.get('target_move_id') or mapped('stock.move',mid):errors.append('existing_mapping_requires_audit')
            for x in details:
                for model,field in [('product.product','product_id'),('uom.uom','product_uom_id'),('stock.location','location_id'),('stock.location','location_dest_id'),('stock.lot','lot_id')]:
                    if x[field] and not mapped(model,rid(x[field])):errors.append('missing_'+model)
                if x['package_id'] or x['result_package_id'] or x['owner_id']:errors.append('package_owner_requires_adapter')
                if loc[rid(x['location_id'])]['usage']=='internal':needs[key(x)]+=qty(x,True)
            shortage=[dict(source_key=list(k),available_historical=pool[k],required=q,shortage=q-pool[k]) for k,q in needs.items() if pool[k]+1e-6<q]
            if shortage:errors.append('historical_supply_shortage')
            if c['category']=='unbuild':errors.append('native_unbuild_adapter_required')
            rows.append(dict(source_move=mid,category=c['category'],name=m['name'],date_utc=m['date'],source_product=m['product_id'],source_unbuild=rid(m.get('unbuild_id')) or rid(m.get('consume_unbuild_id')),return_origin=rid(m.get('origin_returned_move_id')),errors=sorted(set(errors)),shortages=shortage,source_lines=details,preflight_candidate=not errors))
        # Never credit an unresolved output merely because its source is Done.
        for x in details:
            if loc[rid(x['location_id'])]['usage']=='internal':pool[key(x)]-=qty(x,True)
            if c['status']=='verified' and loc[rid(x['location_dest_id'])]['usage']=='internal':pool[key(x,False)]+=qty(x)
    result=dict(month='2026-08',read_only=True,erp_calls=0,coverage_generated_utc=load('after-run-stock-coverage.json')['generated_utc'],rows=rows,summary=dict(moves=len(rows),candidate_scrap=sum(x['preflight_candidate'] for x in rows),reasons=dict(Counter(e for x in rows for e in x['errors']))))
    I['save']('phases/august-scrap-unbuild-preflight.json',result);print(json.dumps(result['summary']),flush=True)
if __name__=='__main__':main()
