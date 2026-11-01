"""Replay the evidenced six-picking closed return loop without extra stock credits."""
from complete_pysb_stock_migration import Completion,rid,index,load,OUT
from execute_pysb_stock_migration import save,require
from collections import defaultdict
import json,sys
def main():
 m=Completion();d=load('supporting-stock-discovery.json');ps=m.a.read('stock.picking',[185317,185318],list(d['pickings'][0].keys()));ms=m.a.read('stock.move',[i for p in ps for i in p['move_lines']],list(d['moves'][0].keys()));ls=m.a.read('stock.move.line',[i for s in ms for i in s['move_line_ids']],list(d['lines'][0].keys()))
 require(all(p['state']=='done' and rid(p['company_id'])==1 for p in ps),'Source mismatch')
 for k,rows in [('pickings',ps),('moves',ms),('lines',ls)]:
  known={x['id'] for x in d[k]};d[k].extend(x for x in rows if x['id'] not in known)
 for x in ls:
  for model,field in [('product.product','product_id'),('uom.uom','product_uom_id'),('stock.location','location_id'),('stock.location','location_dest_id'),('stock.lot','lot_id')]:require(not x[field] or rid(x[field]) in m.maps[model],'Missing mapping')
 save(OUT/'supporting-stock-discovery.json',d)
 if '--complete' not in sys.argv:print(json.dumps({'added_source_pickings':[p['name'] for p in ps],'added_moves':len(ms)}));return
 source_ids={185315,185316,185317,185318,185319,185320};rs=[r for r in m.j['supporting_source_transfers'] if r['source_picking'] in source_ids];targets=sorted({r['target_picking'] for r in rs});require(len(targets)==6,'Incomplete closed loop')
 net=defaultdict(float)
 for r in rs:
  for k,q in r['deltas']:net[tuple(k)]+=q
 require(all(abs(q)<1e-6 for q in net.values()),'Loop changes quantity/location/lot/package/owner')
 def balance():return m.ledger(m.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','package_id','owner_id','quantity']))
 states=m.b.read('stock.picking',targets,['state']);require(all(p['state']!='cancel' for p in states),'Cancelled loop picking')
 pending={p['id'] for p in states if p['state']!='done'};pending_net=defaultdict(float)
 for r in rs:
  if r['target_picking'] in pending:
   for k,q in r['deltas']:pending_net[tuple(k)]+=q
 require(all(abs(q)<1e-6 for q in pending_net.values()),'Remaining loop not zero-net; do not proceed')
 targets=sorted(pending);require(targets,'Loop already done; verify dates instead')
 before=balance();rec={'source_pickings':sorted(source_ids),'target_pickings':targets,'status':'intent','net_deltas':[[list(k),q] for k,q in net.items()],'before':[[list(k),before[k]] for k in net],'reason':'Closed original sale/return loop on 22 July. Source MO 506401 supplied 2 units before the loop. Later deliveries already consumed the available physical stock on staging. Execute the complete zero-net loop in one native transaction; no inventory credit, no duplicate material consumption.'};m.j.setdefault('closed_return_chain_operations',[]).append(rec);m.persist()
 result=m.mutate('stock.picking','button_validate',[targets],{'context':{'skip_backorder':True,'skip_redirection':True,'picking_ids_not_to_backorder':targets}})
 require(not isinstance(result,dict) or not result.get('res_model'),'Wizard returned: inspect state before retry')
 after=balance();actual=m.b.read('stock.picking',targets,['state']);require(all(p['state']=='done' for p in actual),'Incomplete native loop');require(all(abs(after[k]-before[k])<1e-6 for k in net),'Closed loop changed stock')
 rec.update(status='native_done_pending_dates',after=[[list(k),after[k]] for k in net]);m.persist();print(json.dumps({'native_done_pickings':len(targets),'stock_quantity_change':0}))
if __name__=='__main__':main()
