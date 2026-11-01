"""Replay complete source inventory/product groups including both sides of lot swaps."""
from complete_pysb_stock_migration import Completion,rid,require,index,load,OUT
from collections import defaultdict
from xmlrpc.client import Fault
import json
def main():
 m=Completion();d=load('supporting-stock-discovery.json');require(not d.get('discovery_only'), 'Discovery-only coverage: review category, dependencies and approve an execution change set before replay');m.uoms=index(m.b.search_read('uom.uom',[],['factor','rounding']))
 lines=defaultdict(list)
 for x in d['lines']:
  if x['qty_done']>0:lines[rid(x['move_id'])].append(x)
 known={x['source_move'] for x in m.j.get('supplementary_inventory_adjustments',[])};groups=defaultdict(list)
 for s in d['moves']:
  if not s['picking_id']:groups[(rid(s.get('inventory_id')),rid(s['product_id']))].append(s)
 pending=[]
 for group,sources in sorted(groups.items(),key=lambda g:min(x['date'] for x in g[1])):
  todo=[s for s in sources if s['id'] not in known]
  if not todo:continue
  physical=m.ledger(m.b.search_read('stock.quant',[['company_id','=',1],['product_id','=',m.maps['product.product'][group[1]]]],['product_id','location_id','lot_id','owner_id','package_id','quantity']))
  negative=defaultdict(float)
  for s in todo:
   for x in lines[s['id']]:
    require(not x['owner_id'] and not x['package_id'] and not x['result_package_id'],'Inventory package/owner requires review')
    if rid(x['location_dest_id'])==14:negative[m.quantkey(x)]+=m.qty(x)
    else:require(rid(x['location_id'])==14,'Not inventory move')
  shortages=[{'key':list(k),'required':v,'available':physical[k]} for k,v in negative.items() if physical[k]+1e-6<v]
  if shortages:pending.append({'inventory_product':group,'source_moves':[s['id'] for s in todo],'shortages':shortages});continue
  for s in sorted(todo,key=lambda s:(s['date'],s['id'])):
   require(len(lines[s['id']])==1,'Inventory source split requires review');x=lines[s['id']][0];out=rid(x['location_dest_id'])==14;key=m.quantkey(x,not out);pid,loc,lot,pkg,owner=key;delta=m.qty(x)*(-1 if out else 1)
   require(not m.b.search_read('ir.model.data',[['module','=','pysb_v14'],['name','=','stock_move_'+str(s['id'])]],['id']),'Unjournalled external inventory move')
   domain=[['company_id','=',1],['product_id','=',pid],['is_inventory','=',True]];before=m.b.call('stock.move','search',[domain])
   qdomain=[['company_id','=',1],['product_id','=',pid],['location_id','=',loc],['lot_id','=',lot],['package_id','=',False],['owner_id','=',False]]
   q=m.b.search_read('stock.quant',qdomain,['quantity']);require(len(q)<=1,'Multiple stock quants')
   current=q[0]['quantity'] if q else 0;require(current+delta>=-1e-6,'Adjustment would create negative stock')
   qid=q[0]['id'] if q else m.mutate('stock.quant','create',[{'product_id':pid,'location_id':loc,'lot_id':lot}],{'context':{'inventory_mode':True}})
   note={'purpose':'REAL SOURCE INVENTORY ADJUSTMENT / NOT TEMPORARY','source_database':m.a.db,'company_id':1,'source_move':s,'source_line':x,'inventory_product_group':group,'before':current,'delta':delta}
   op={'source_move':s['id'],'status':'intent','note':note};m.j.setdefault('supporting_adjustment_operations',[]).append(op);m.persist()
   m.mutate('stock.quant','write',[[qid],{'inventory_quantity':current+delta}],{'context':{'inventory_mode':True}})
   try:m.mutate('stock.quant','action_apply_inventory',[[qid]],{'context':{'inventory_mode':True,'inventory_name':f"PYSB-SOURCE-ADJ | v14 {s['id']} | {s['name']}"}})
   except Fault as e:
    if 'cannot marshal None' not in str(e):raise
   new=m.b.search_read('stock.move',domain,['state','quantity','location_id','location_dest_id','move_line_ids']);new=[a for a in new if a['id'] not in before]
   require(len(new)==1 and new[0]['state']=='done' and abs(new[0]['quantity']-abs(delta))<1e-6,'Uncertain adjustment result');v=new[0]
   require(rid(v['location_id'])==(loc if out else 11) and rid(v['location_dest_id'])==(11 if out else loc),'Wrong adjustment route')
   m.mutate('stock.move','write',[[v['id']],{'date':s['date'],'origin':f"PYSB-SOURCE-ADJ | v14 {s['id']}",'description_picking_manual':json.dumps(note,ensure_ascii=False)}]);m.mutate('stock.move.line','write',[v['move_line_ids'],{'date':s['date']}]);m.attach('stock.move',[(s['id'],v['id'])])
   require(abs(sum(z['quantity'] for z in m.b.search_read('stock.quant',qdomain,['quantity']))-current-delta)<1e-6,'Adjustment quantity mismatch')
   m.j.setdefault('supplementary_inventory_adjustments',[]).append({'source_move':s['id'],'target_move':v['id'],'source_qty':s['quantity_done'],'target_qty':abs(delta),'date':s['date'],'deltas':[[list(key),delta],[[pid,11,lot,False,False],-delta]],'reference':s['name'],'group':group});op.update(status='verified',target_move=v['id']);m.persist();print(json.dumps({'source':s['id'],'target':v['id'],'delta':delta}),flush=True)
 m.j['supporting_adjustment_pending']=pending;m.persist();print(json.dumps({'pending_groups':pending}),flush=True)
if __name__=='__main__':main()
