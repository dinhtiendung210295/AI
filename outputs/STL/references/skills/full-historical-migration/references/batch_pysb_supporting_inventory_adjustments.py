"""Native inventory application in disjoint batches, preserving source pair groups."""
from complete_pysb_stock_migration import Completion,rid,require,index,load,OUT
from execute_pysb_stock_migration import save
from collections import defaultdict
from xmlrpc.client import Fault
import json
def main():
 m=Completion();d=load('supporting-stock-discovery.json');require(not d.get('discovery_only'), 'Discovery-only coverage: review category, dependencies and approve an execution change set before replay');m.uoms=index(m.b.search_read('uom.uom',[],['factor','rounding']));known={r['source_move'] for r in m.j.get('supplementary_inventory_adjustments',[])};lines=defaultdict(list);groups=defaultdict(list)
 for x in d['lines']:
  if x['qty_done']>0:lines[rid(x['move_id'])].append(x)
 for s in d['moves']:
  if not s['picking_id'] and s['id'] not in known:groups[(rid(s.get('inventory_id')),rid(s['product_id']))].append(s)
 all_pending=[]
 while groups:
  quants=m.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','package_id','owner_id','quantity']);bykey=defaultdict(list)
  for q in quants:bykey[tuple(rid(q[k]) for k in ['product_id','location_id','lot_id','package_id','owner_id'])].append(q)
  chosen=[];used=set();pending=[]
  for group,ss in sorted(groups.items(),key=lambda g:min(s['date'] for s in g[1])):
   entries=[];negative=defaultdict(float);bad=[]
   for s in sorted(ss,key=lambda s:(s['date'],s['id'])):
    require(len(lines[s['id']])==1,'Inventory split needs review');x=lines[s['id']][0];out=rid(x['location_dest_id'])==14;require(out or rid(x['location_id'])==14,'Not inventory flow');key=m.quantkey(x,not out);delta=m.qty(x)*(-1 if out else 1)
    require(not key[3] and not key[4],'Inventory package/owner requires review')
    if not m.product[key[0]]['is_storable']:bad.append('Target product is not storable')
    if m.product[key[0]]['tracking']!='none' and not key[2]:bad.append('Missing tracked lot')
    if m.product[key[0]]['tracking']=='serial' and abs(abs(delta)-1)>1e-6:bad.append('Serial quantity is not one')
    if delta<0:negative[key]-=delta
    entries.append({'source':s,'line':x,'key':key,'delta':delta})
   keys={e['key'] for e in entries};short=[{'key':list(k),'required':v,'available':sum(q['quantity'] for q in bykey[k])} for k,v in negative.items() if sum(q['quantity'] for q in bykey[k])+1e-6<v]
   if bad or short:pending.append({'inventory_product':group,'source_moves':[s['id'] for s in ss],'reason':bad,'shortages':short});continue
   if len(keys)!=len(entries):pending.append({'inventory_product':group,'source_moves':[s['id'] for s in ss],'reason':['Same-quant source adjustment needs sequential replay'],'shortages':[]});continue
   if keys & used:continue
   require(all(len(bykey[k])<=1 for k in keys),'Multiple inventory quants')
   chosen.append((group,entries));used.update(keys)
   if len(used)>=50:break
  if not chosen:all_pending=pending;break
  entries=[e for g,es in chosen for e in es];require(all(abs(e['delta'])>1e-8 for e in entries),'Rounded-to-zero inventory requires explicit record')
  missing=[e for e in entries if not bykey[e['key']]]
  if missing:
   vals=[{'product_id':e['key'][0],'location_id':e['key'][1],'lot_id':e['key'][2]} for e in missing];ids=m.mutate('stock.quant','create',[vals],{'context':{'inventory_mode':True,'allowed_company_ids':[1]}});require(len(ids)==len(vals),'Quant creation incomplete')
   for e,qid in zip(missing,ids):bykey[e['key']]=[{'id':qid,'quantity':0.0}]
  for e in entries:e['quant_id']=bykey[e['key']][0]['id'];e['before']=bykey[e['key']][0]['quantity']
  pids=sorted({e['key'][0] for e in entries});domain=[['company_id','=',1],['product_id','in',pids],['is_inventory','=',True]];before=m.b.call('stock.move','search',[domain])
  record={'status':'intent','entries':entries,'source_groups':[list(g) for g,es in chosen]};m.j.setdefault('batched_source_inventory_operations',[]).append(record);m.persist()
  data=[[str(e['quant_id']),str(round(e['before']+e['delta'],5))] for e in entries]
  m.mutate('stock.quant','load',[['.id','inventory_quantity'],data],{'context':{'inventory_mode':True,'allowed_company_ids':[1],'tz':'UTC'}})
  try:m.mutate('stock.quant','action_apply_inventory',[[e['quant_id'] for e in entries]],{'context':{'inventory_mode':True,'allowed_company_ids':[1],'inventory_name':'PYSB-SOURCE-ADJ / real July v14 transactions'}})
  except Fault as exc:
   if 'cannot marshal None' not in str(exc):raise
  new=[v for v in m.b.search_read('stock.move',domain,['state','quantity','product_id','location_id','location_dest_id','move_line_ids']) if v['id'] not in before];require(len(new)==len(entries) and all(v['state']=='done' for v in new),'Batch inventory result uncertain')
  detail=index(m.b.read('stock.move.line',[i for v in new for i in v['move_line_ids']],['lot_id','quantity_product_uom','product_id','location_id','location_dest_id']));usedmoves=set()
  for e in entries:
   pid,loc,lot,_,_=e['key'];src,dst=(loc,11) if e['delta']<0 else (11,loc)
   hits=[v for v in new if v['id'] not in usedmoves and rid(v['product_id'])==pid and rid(v['location_id'])==src and rid(v['location_dest_id'])==dst and abs(v['quantity']-abs(e['delta']))<1e-6 and all(rid(detail[i]['lot_id'])==lot for i in v['move_line_ids'])];require(len(hits)==1,'Ambiguous source inventory result');v=hits[0];usedmoves.add(v['id']);e['target_move']=v['id'];e['target_lines']=v['move_line_ids']
  record['status']='native_done_pending_dates';m.persist()
  refs=[];dates=[];pairs=[]
  for e in entries:
   s=e['source'];ref=f"PYSB-SOURCE-ADJ | v14 {s['id']} | {s['name']}";note=json.dumps({'purpose':'REAL SOURCE INVENTORY ADJUSTMENT / NOT TEMPORARY','source_move':s,'source_line':e['line'],'target_key':e['key'],'before':e['before'],'delta':e['delta']},ensure_ascii=False)
   refs.append([e['target_move'],s['date'],ref,ref,note]);dates.extend([[i,s['date']] for i in e['target_lines']]);pairs.append((s['id'],e['target_move']))
  m.matrix('stock.move',['.id','date','origin','inventory_name','description_picking_manual'],refs);m.matrix('stock.move.line',['.id','date'],dates);m.attach('stock.move',pairs)
  after=m.b.read('stock.quant',[e['quant_id'] for e in entries],['quantity']);qvalues={q['id']:q['quantity'] for q in after}
  for e in entries:
   require(abs(qvalues[e['quant_id']]-e['before']-e['delta'])<1e-6,'Wrong source inventory delta');s=e['source'];pid,loc,lot,_,_=e['key']
   m.j.setdefault('supplementary_inventory_adjustments',[]).append({'source_move':s['id'],'target_move':e['target_move'],'source_qty':s['quantity_done'],'target_qty':abs(e['delta']),'date':s['date'],'reference':s['name'],'deltas':[[list(e['key']),e['delta']],[[pid,11,lot,False,False],-e['delta']]]})
  record['status']='verified';m.persist()
  for g,es in chosen:groups.pop(g)
  print(json.dumps({'verified_source_adjustments':len(entries),'remaining_source_groups':len(groups)}),flush=True)
 m.j['supporting_adjustment_pending']=all_pending;m.persist();save(OUT/'other-stock-adjustment-result.json',{'pending':all_pending,'verified_total':len(m.j.get('supplementary_inventory_adjustments',[]))});print(json.dumps({'pending_groups':len(all_pending),'pending':all_pending}),flush=True)
if __name__=='__main__':main()
