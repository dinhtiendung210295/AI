"""Read-only root availability; retain all held candidates with reasons."""
import json,runpy
from collections import defaultdict,Counter
from pathlib import Path
M=runpy.run_path(str(Path(__file__).with_name('migrate_pysb_independent_deliveries.py')))
def main():
    r=M['Run']();rid=M['rid'];rows=[x for x in r.planrows if x['eligible'] and str(x['source_so']) not in r.j['groups']]
    pids={r.maps['product.product'][rid(r.sm[mid]['product_id'])] for x in rows for mid in x['roots']}
    quants=r.b.scan('stock.quant',[['company_id','=',1],['product_id','in',sorted(pids)],['package_id','=',False],['owner_id','=',False]],['product_id','location_id','lot_id','quantity','reserved_quantity'])
    pool=defaultdict(lambda:[0.,0.])
    for x in quants:
        key=tuple(rid(x[f]) for f in ['product_id','location_id','lot_id']);pool[key][0]+=x['quantity'];pool[key][1]+=x['reserved_quantity']
    results=[]
    for row in rows:
        demand=defaultdict(float);errors=[]
        for mid in row['roots']:
            for line in r.by_move[mid]:
                lot=rid(line['lot_id']);tl=r.maps.get('stock.lot',{}).get(lot,False)
                if lot and not tl:errors.append('lot_not_mapped');continue
                p=r.maps['product.product'][rid(line['product_id'])];u=r.maps['uom.uom'][rid(line['product_uom_id'])]
                key=(p,r.maps['stock.location'][rid(line['location_id'])],tl)
                demand[key]+=M['R']['rounded'](line['qty_done'],r.tu[u]['rounding'])*r.tu[u]['factor']/r.tu[rid(r.tp[p]['uom_id'])]['factor']
        for key,q in demand.items():
            if pool[key][0]-pool[key][1]+1e-6<q:errors.append('insufficient_unreserved_exact_stock')
        results.append(dict(source_so=row['source_so'],name=row['name'],eligible=not errors,errors=sorted(set(errors)),demand=[dict(key=list(k),needed=v,quantity=pool[k][0],reserved=pool[k][1]) for k,v in demand.items()]))
    report=dict(read_only=True,rows=results,summary=dict(candidates=len(rows),free_candidates=sum(x['eligible'] for x in results),holds=dict(Counter(e for x in results for e in x['errors']))))
    M['save']('stock-free-delivery-candidates.json',report);print(json.dumps(report['summary']),flush=True)
    print(json.dumps([x for x in results if x['eligible']][:5]),flush=True)
if __name__=='__main__':main()
