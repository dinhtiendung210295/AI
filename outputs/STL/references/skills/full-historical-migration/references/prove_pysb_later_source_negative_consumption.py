"""Find already-replayed source-negative consumption explaining physical shortages."""
from complete_pysb_stock_migration import Completion,rid,require,index,OUT
from execute_pysb_stock_migration import save
from collections import defaultdict
import json
def main():
 m=Completion();keys=[(49735,8,35913,False,False),(48363,99,32572,False,False),(49126,8,31200,False,False)];pids=[k[0] for k in keys]
 products=index(m.a.read('product.product',pids,['uom_id','name']));uoms=index(m.a.search_read('uom.uom',[],['factor','rounding']))
 qs=m.a.search_read('stock.quant',[['company_id','=',1],['product_id','in',pids]],['product_id','location_id','lot_id','package_id','owner_id','quantity'])
 ls=m.a.search_read('stock.move.line',[['company_id','=',1],['product_id','in',pids],['state','=','done'],['move_id.date','>=','2026-06-30 16:00:00'],['qty_done','>',0]],['move_id','product_id','product_uom_id','qty_done','lot_id','location_id','location_dest_id','package_id','result_package_id','owner_id'])
 ms=index(m.a.read('stock.move',sorted({rid(x['move_id']) for x in ls}),['date','picking_id','name']));balances=defaultdict(float)
 for q in qs:balances[tuple(rid(q[k]) for k in ['product_id','location_id','lot_id','package_id','owner_id'])]+=q['quantity']
 changes=defaultdict(lambda:defaultdict(float));parts=defaultdict(list)
 for x in ls:
  qty=x['qty_done']*uoms[rid(products[rid(x['product_id'])]['uom_id'])]['factor']/uoms[rid(x['product_uom_id'])]['factor'];mid=rid(x['move_id']);parts[mid].append(x)
  a=(rid(x['product_id']),rid(x['location_id']),rid(x['lot_id']),rid(x['package_id']),rid(x['owner_id']));b=(rid(x['product_id']),rid(x['location_dest_id']),rid(x['lot_id']),rid(x['result_package_id']),rid(x['owner_id']))
  changes[mid][a]-=qty;changes[mid][b]+=qty
 for cs in changes.values():
  for k,v in cs.items():balances[k]-=v
 proof=[]
 for mid in sorted(changes,key=lambda i:(ms[i]['date'],i)):
  for k,v in changes[mid].items():
   if k in keys and v<0 and balances[k]+v < -1e-6:
    target=m.maps['stock.move'].get(mid);event=m.j['event_results'].get('picking:'+str(rid(ms[mid]['picking_id'])),{})
    if target and event.get('status')=='done':proof.append({'source_move':mid,'source_document':ms[mid]['picking_id'],'date':ms[mid]['date'],'source_key':list(k),'source_before':balances[k],'source_consumption':-v,'negative_portion':min(-v,max(0,-balances[k]-v)),'target_move':target,'event':event,'source_lines':parts[mid]})
  for k,v in changes[mid].items():balances[k]+=v
 save(OUT/'later-source-negative-consumption-proof.json',proof);print(json.dumps(proof))
if __name__=='__main__':main()
