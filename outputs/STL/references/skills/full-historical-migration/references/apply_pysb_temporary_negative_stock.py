"""Approved temporary stock, only for evidenced source-negative pending lines."""
import runpy,json,math
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from xmlrpc.client import Fault
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/complete_pysb_stock_migration.py'))
def main():
 m=H['Completion']();rid=H['rid'];require=H['require'];m.prepare_validation();evidence=H['load']('source-negative-stock-classification.json');rows=[x for x in evidence['rows'] if x['source_would_be_negative']]
 grouping=defaultdict(list)
 for row in rows:grouping[(m.eventkey(row['event']),tuple(row['target_key']))].append(row)
 qfields=['product_id','location_id','lot_id','package_id','owner_id','quantity'];current=m.ledger(m.b.search_read('stock.quant',[['company_id','=',1]],qfields));required_so_far=defaultdict(float);credits=defaultdict(float);plan=[]
 for (eventkey,key),parts in sorted(grouping.items(),key=lambda item:(item[1][0]['event']['date'],item[1][0]['source_move'])):
  event=parts[0]['event'];source_ids={x['source_move'] for x in parts};needed=sum(m.qty(x) for x in m.expected(event) if rid(x['move_id']) in source_ids and m.quantkey(x)==key);required_so_far[key]+=needed
  hist=parts[0]['target_shortage'].get('historical_available');require(hist is not None,'Historical stock evidence missing')
  deficit=max(0.0,required_so_far[key]-current[key]-credits[key],required_so_far[key]-hist-credits[key]);delta=math.ceil((deficit-1e-8)*100)/100
  if delta<=0:continue
  credits[key]+=delta;date=(datetime.strptime(min(x['source_move_date'] for x in parts),'%Y-%m-%d %H:%M:%S')-timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')
  token='temp_neg_'+str(min(source_ids))+'_'+str(key[0])+'_'+str(key[1])+'_'+str(key[2] or 0)+'_'+str(key[3] or 0)
  plan.append({'token':token,'event':event,'key':key,'date':date,'delta':delta,'source_evidence':parts,'required_so_far':required_so_far[key],'original_target_current':current[key],'original_target_historical':hist})
 H['H']['save'](m.path.parent/'temporary-negative-stock-plan.json',plan)
 pids=sorted({x['key'][0] for x in plan});products=H['index'](m.b.read('product.product',pids,['name','tracking','uom_id','is_storable']));lotids=sorted({x['key'][2] for x in plan if x['key'][2]});lots=H['index'](m.b.read('stock.lot',lotids,['name','product_id','company_id']));locations=H['index'](m.b.read('stock.location',sorted({x['key'][1] for x in plan}),['usage','company_id','complete_name']))
 for item in plan:
  pid,loc,lot,package,owner=item['key'];product=products[pid];require(product['is_storable'] and not owner and locations[loc]['usage']=='internal' and rid(locations[loc]['company_id'])==1,'Unsupported temporary stock dimensions')
  if lot:require(rid(lots[lot]['product_id'])==pid and rid(lots[lot]['company_id']) in [False,1],'Wrong lot')
  require(product['tracking']=='none' or lot,'Cannot invent a required lot')
  require(product['tracking']!='serial' or item['delta']==1,'Serial temporary stock requires separate review')
 m.j.setdefault('temporary_negative_stock_adjustments',[])
 for item in plan:
  existing=next((x for x in m.j['temporary_negative_stock_adjustments'] if x['token']==item['token']),None)
  if existing:
   require(existing['status']=='verified','Interrupted temporary adjustment requires read-back review');continue
  pid,loc,lot,package,owner=item['key'];delta=item['delta'];product=products[pid];event=item['event'];lotname=lots[lot]['name'] if lot else 'NONE';reference=f"PYSB-TEMP-NEG | v14 {event['reference']} | moves {','.join(str(x['source_move']) for x in item['source_evidence'])} | lot {lotname} | +{delta} {product['uom_id'][1]} | REVIEW REQUIRED"
  external=m.b.call('ir.model.data','search_read',[[['module','=','pysb_temporary_inventory'],['name','=',item['token']]]],{'fields':['res_id']});require(not external,'Unjournaled temporary external ID; review before continuing')
  domain=[['company_id','=',1],['product_id','=',pid],['is_inventory','=',True]];before=m.b.call('stock.move','search',[domain]);qdomain=[['company_id','=',1],['product_id','=',pid],['location_id','=',loc],['lot_id','=',lot],['package_id','=',package],['owner_id','=',False]];quants=m.b.search_read('stock.quant',qdomain,['quantity']);require(len(quants)<=1,'Multiple quants require review')
  if not quants:qid=m.mutate('stock.quant','create',[{'product_id':pid,'location_id':loc,'lot_id':lot,'package_id':package}],{'context':{'inventory_mode':True}});qty=0.0
  else:qid=quants[0]['id'];qty=quants[0]['quantity']
  record={**item,'key':list(item['key']),'reference':reference,'approved_by':'Bruce','approved_at_utc':datetime.now(timezone.utc).isoformat(),'before_quantity':qty,'review_status':'TEMPORARY_PENDING_RECONCILIATION','not_an_actual_v14_inventory_adjustment':True,'status':'intent'};m.j['temporary_negative_stock_adjustments'].append(record);m.persist()
  m.mutate('stock.quant','write',[[qid],{'inventory_quantity':qty+delta}],{'context':{'inventory_mode':True}})
  try:m.mutate('stock.quant','action_apply_inventory',[[qid]],{'context':{'inventory_mode':True,'inventory_name':reference}})
  except Fault as exc:
   if 'cannot marshal None' not in str(exc):raise
  new=[x for x in m.b.search_read('stock.move',domain,['state','quantity','location_id','location_dest_id','move_line_ids']) if x['id'] not in before];require(len(new)==1 and new[0]['state']=='done' and abs(new[0]['quantity']-delta)<1e-6 and rid(new[0]['location_dest_id'])==loc,'Temporary inventory result uncertain')
  move=new[0];note=json.dumps({'purpose':'TEMPORARY STOCK TO REPLAY V14 NEGATIVE STOCK; NOT A REAL V14 ADJUSTMENT','review_status':'TEMPORARY_PENDING_RECONCILIATION','approved_by':'Bruce','source_database':m.a.db,'target_database':m.b.db,'company_id':1,'source_document':event['reference'],'source_event_id':event['source'],'target_document_id':event['target'],'source_move_ids':[x['source_move'] for x in item['source_evidence']],'source_line_ids':[i for x in item['source_evidence'] for i in x['source_line_ids']],'product':product['name'],'product_id':pid,'location':locations[loc]['complete_name'],'lot':lotname,'temporary_quantity':delta,'unit':product['uom_id'][1],'effective_utc':item['date'],'actual_created_utc':record['approved_at_utc'],'minimum_quantity_calculation':{k:item[k] for k in ['required_so_far','original_target_current','original_target_historical']},'source_negative_evidence':item['source_evidence'],'followup':'Identify authoritative stock correction and reconcile/remove temporary impact via a tracked transaction; do not blindly cancel validated documents.'},ensure_ascii=False,indent=2)
  m.mutate('stock.move','write',[[move['id']],{'date':item['date'],'origin':reference,'description_picking_manual':note,'inventory_name':reference}]);m.mutate('stock.move.line','write',[move['move_line_ids'],{'date':item['date']}]);m.mutate('ir.model.data','create',[{'module':'pysb_temporary_inventory','name':item['token'],'model':'stock.move','res_id':move['id'],'noupdate':True}])
  actual=m.b.search_read('stock.quant',qdomain,['quantity']);require(abs(sum(x['quantity'] for x in actual)-(qty+delta))<1e-6,'Wrong temporary quantity');saved=m.b.read('stock.move',[move['id']],['origin','description_picking_manual','inventory_name','date'])[0];require(saved['origin']==reference and saved['description_picking_manual']==note and saved['date']==item['date'],'Reference note was not preserved')
  record.update(status='verified',target_move=move['id'],after_quantity=qty+delta,note=note,deltas=[[[pid,rid(move['location_id']),lot,False,False],-delta],[list(item['key']),delta]]);m.persist();print(json.dumps({'temporary_move':move['id'],'reference':reference,'delta':delta,'status':'verified'}),flush=True)
 # Retry only affected source-negative events and their existing downstream chain.
 eligible={m.eventkey(row['event']) for row in rows};source_events={m.eventkey(e):e for e in m.j['event_results'].values()};mids=set()
 for key in eligible:
  event=source_events[key]
  for x in m.expected(event):mids.add(rid(x['move_id']))
 for _ in range(16):
  previous=len(mids)
  for mid in list(mids):
   source=m.sm.get(mid) or m.mm[mid]
   mids.update(i for i in source['move_dest_ids'] if i in m.sm or i in m.mm)
  if len(mids)==previous:break
 for mid in mids:
  source=m.sm.get(mid) or m.mm[mid];picking=rid(source.get('picking_id'));production=rid(source.get('raw_material_production_id')) or rid(source.get('production_id'));key='picking:'+str(picking) if picking else 'mo:'+str(production)
  if key in source_events:eligible.add(key)
 H['H']['save'](m.path.parent/'temporary-negative-stock-retry-keys.json',sorted(eligible));H['H']['save'](m.path.parent/'temporary-negative-stock-report.json',{'adjustments':m.j['temporary_negative_stock_adjustments'],'retry_event_keys':sorted(eligible),'source_classification':evidence['summary']});print(json.dumps({'temporary_adjustments':len(plan),'affected_event_keys':len(eligible)}),flush=True)
if __name__=='__main__':main()
