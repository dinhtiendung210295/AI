"""Operator-approved opening corrections for five evidenced products only."""
from complete_pysb_stock_migration import Completion,rid,require,index,load,OUT
from execute_pysb_stock_migration import save
from collections import defaultdict
from xmlrpc.client import Fault
import json
def main():
 m=Completion();wanted=[51399,52643,47229,51715,54103];targetids=[m.maps['product.product'][s] for s in wanted]
 aliases=[(35558,26447,'4206C90321 ','4206C90321'),(35979,25747,'LOT01-2','LOT01-2 (BISON)')]
 for sid,tid,srcname,targetname in aliases:
  require(m.b.read('stock.lot',[tid],['name'])[0]['name']==targetname,'Cleaned lot changed')
  before=m.maps['stock.lot'][sid]
  if before!=tid:
   source_lines=[x for x in m.sl.values() if rid(x['lot_id'])==sid and x['id'] in m.maps['stock.move.line']]
   tids=[m.maps['stock.move.line'][x['id']] for x in source_lines]
   actual=m.b.read('stock.move.line',tids,['state','lot_id']);require(all(x['state']!='done' and rid(x['lot_id'])==before for x in actual),'Alias affects completed or changed line')
   if tids:m.mutate('stock.move.line','write',[tids,{'lot_id':tid}])
   external=m.b.search_read('ir.model.data',[['module','=','pysb_v14'],['name','=','stock_lot_'+str(sid)]],['res_id']);require(len(external)==1 and external[0]['res_id']==before,'External lot alias mismatch')
   m.mutate('ir.model.data','write',[[external[0]['id']],{'res_id':tid}]);m.maps['stock.lot'][sid]=tid
   m.j.setdefault('approved_opening_lot_aliases',[]).append({'source_lot':sid,'old_target':before,'target_lot':tid,'source_name':srcname,'target_name':targetname,'reason':'Operator approved cleaned lot alias, stock quantity unchanged'});m.persist()
 rows=[r for r in load('lot-opening-closing-report.json')['rows'] if r['source_product'] in wanted and r['source_opening']>1e-6]
 lots=m.b.search_read('stock.lot',[['company_id','=',1],['product_id','in',targetids]],['name','product_id']);byname={(rid(x['product_id']),x['name']):x['id'] for x in lots};desired=defaultdict(float)
 for r in rows:
  name=r['lot'];name={'4206C90321 ':'4206C90321','LOT01-2':'LOT01-2 (BISON)'}.get(name,name);pid=r['target_product'];require((pid,name) in byname,'Opening lot not mapped')
  desired[(pid,5,byname[pid,name],False,False)]+=r['source_opening']
 baseline=m.ledger([q for q in m.j['baseline_quants'] if rid(q['product_id']) in targetids and rid(q['location_id'])==5])
 deltas={k:desired[k]-baseline[k] for k in set(desired)|set(baseline) if abs(desired[k]-baseline[k])>1e-6}
 date='2026-06-30 15:59:59';existing=m.j.setdefault('opening_stock_corrections',[])
 for key,delta in sorted(deltas.items(),key=lambda kv:kv[1]):
  if any(tuple(r['key'])==key and r['status']=='verified' for r in existing):continue
  pid,loc,lot,pkg,owner=key;require(not pkg and not owner,'Opening package/owner unsupported')
  qdomain=[['company_id','=',1],['product_id','=',pid],['location_id','=',loc],['lot_id','=',lot],['package_id','=',False],['owner_id','=',False]]
  qs=m.b.search_read('stock.quant',qdomain,['quantity']);require(len(qs)<=1,'Multiple opening quants');current=qs[0]['quantity'] if qs else 0;require(current+delta>=-1e-6,'Opening correction would create negative stock')
  domain=[['company_id','=',1],['product_id','=',pid],['is_inventory','=',True]];before=m.b.call('stock.move','search',[domain]);qid=qs[0]['id'] if qs else m.mutate('stock.quant','create',[{'product_id':pid,'location_id':loc,'lot_id':lot}],{'context':{'inventory_mode':True}})
  rec={'key':list(key),'delta':delta,'date':date,'status':'intent','source_opening':desired[key],'target_baseline':baseline[key],'note':'Operator approved opening repair based on native v14 June-30 lot balance; real opening correction, not temporary supply','before':current};existing.append(rec);m.persist()
  m.mutate('stock.quant','write',[[qid],{'inventory_quantity':current+delta}],{'context':{'inventory_mode':True}})
  try:m.mutate('stock.quant','action_apply_inventory',[[qid]],{'context':{'inventory_mode':True,'inventory_name':f'PYSB-OPENING-CORRECTION | product {pid} | lot {lot} | source 2026-06-30'}})
  except Fault as e:
   if 'cannot marshal None' not in str(e):raise
  new=m.b.search_read('stock.move',domain,['state','quantity','location_id','location_dest_id','move_line_ids']);new=[x for x in new if x['id'] not in before];require(len(new)==1 and new[0]['state']=='done' and abs(new[0]['quantity']-abs(delta))<1e-6,'Opening adjustment uncertain');v=new[0]
  require(rid(v['location_id'])==(loc if delta<0 else 11) and rid(v['location_dest_id'])==(11 if delta<0 else loc),'Opening adjustment route mismatch')
  m.mutate('stock.move','write',[[v['id']],{'date':date,'origin':'PYSB-OPENING-CORRECTION / OPERATOR APPROVED','description_picking_manual':json.dumps(rec,ensure_ascii=False)}]);m.mutate('stock.move.line','write',[v['move_line_ids'],{'date':date}])
  rec.update(status='verified',target_move=v['id'],deltas=[[list(key),delta],[[pid,11,lot,False,False],-delta]]);m.persist();print(json.dumps({'opening_key':key,'delta':delta,'target_move':v['id']}),flush=True)
 # Original opening imports were dated July 1: align their dates, not quantities.
 if not m.j.get('approved_five_product_opening_dates'):
  initial=m.b.search_read('stock.move',[['company_id','=',1],['product_id','in',targetids],['is_inventory','=',True],['state','=','done'],['id','<',11600]],['date','quantity','location_id','location_dest_id','move_line_ids'])
  sums=defaultdict(float)
  detail=m.b.read('stock.move.line',[i for v in initial for i in v['move_line_ids']],['product_id','location_id','location_dest_id','lot_id','quantity_product_uom'])
  for x in detail:
   key=(rid(x['product_id']),5,rid(x['lot_id']),False,False)
   if rid(x['location_dest_id'])==5:sums[key]+=x['quantity_product_uom']
   if rid(x['location_id'])==5:sums[key]-=x['quantity_product_uom']
  require(all(abs(sums[k]-baseline[k])<1e-6 for k in set(sums)|set(baseline)),'Initial imports do not match baseline quantities')
  m.j['approved_five_product_opening_dates']={'before':initial,'status':'intent','date':date};m.persist()
  m.matrix('stock.move',['.id','date'],[[x['id'],date] for x in initial]);m.matrix('stock.move.line',['.id','date'],[[i,date] for x in initial for i in x['move_line_ids']])
  m.j['approved_five_product_opening_dates']['status']='verified';m.persist()
 print('Five-product opening correction complete',flush=True)
if __name__=='__main__':main()
