"""Complete prepared stock events chronologically and emit a combined quantity audit."""
import argparse,html,json,runpy,traceback
from scan_pysb_july_other_stock_coverage import acceptance_gate
from decimal import Decimal,ROUND_HALF_UP
from datetime import datetime,timezone,timedelta
from collections import defaultdict,Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/execute_pysb_stock_migration.py'))
Migration,require,rid,index,load=[H[k] for k in ['Migration','require','rid','index','load']]
class Completion(Migration):
 def __init__(self):
  super().__init__();self.expected_cache=defaultdict(list)
  for x in self.sl.values():
   if x['qty_done']>0:self.expected_cache['picking:'+str(rid(x['picking_id']))].append(x)
  for x in self.ml.values():
   m=self.mm[rid(x['move_id'])];sid=rid(m['raw_material_production_id']) or rid(m['production_id'])
   if x['qty_done']>0:self.expected_cache['mo:'+str(sid)].append(x)
 def effective_qty(self,x):
  if not self.j.get('approved_two_decimal_rounding'):return x['qty_done']
  return float(Decimal(str(x['qty_done'])).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
 def expected(self,event):
  return self.expected_cache[self.eventkey(event)]
 def quantkey(self,x,dest=False):
  return (self.maps['product.product'][rid(x['product_id'])],self.maps['stock.location'][rid(x['location_dest_id' if dest else 'location_id'])],self.maps['stock.lot'].get(rid(x['lot_id']),False),self.maps.get('stock.package',{}).get(rid(x['result_package_id' if dest else 'package_id']),False),False)
 def ledger(self,rows):
  d=defaultdict(float)
  for x in rows:d[(rid(x['product_id']),rid(x['location_id']),rid(x['lot_id']),rid(x['package_id']),rid(x['owner_id']))]+=x['quantity']
  return d
 def qty(self,x):
  p=self.product[self.maps['product.product'][rid(x['product_id'])]];u=self.uoms[self.maps['uom.uom'][rid(x['product_uom_id'])]];base=self.uoms[rid(p['uom_id'])]
  q=self.effective_qty(x)*u['factor']/base['factor']
  return float(Decimal(str(q)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)) if self.j.get('approved_two_decimal_rounding') else q
 def eventkey(self,e):return e['kind']+':'+str(e['source'])
 def changes(self,e):
  d=defaultdict(float)
  for x in self.expected(e):
   d[self.quantkey(x)]-=self.qty(x);d[self.quantkey(x,True)]+=self.qty(x)
  return d
 def verify_details(self,events):
  mm=self.maps['stock.move'];mids=set()
  for e in events:
   if e['kind']=='picking':mids.update(mm[m['id']] for m in self.sm.values() if rid(m['picking_id'])==e['source'] and m['id'] in mm)
   else:mids.update(mm[i] for i in self.mos[e['source']]['move_raw_ids']+self.mos[e['source']]['move_finished_ids'] if i in mm)
  rows=self.b.search_read('stock.move.line',[['move_id','in',list(mids)],['company_id','=',1]],['move_id','product_id','product_uom_id','location_id','location_dest_id','lot_id','quantity','picked','package_id','result_package_id'])
  expected=defaultdict(float);actual=defaultdict(float)
  for e in events:
   for x in self.expected(e):
    key=(mm[rid(x['move_id'])],self.maps['product.product'][rid(x['product_id'])],self.maps['uom.uom'][rid(x['product_uom_id'])],self.maps['stock.location'][rid(x['location_id'])],self.maps['stock.location'][rid(x['location_dest_id'])],self.maps['stock.lot'].get(rid(x['lot_id']),False),self.maps.get('stock.package',{}).get(rid(x['package_id']),False),self.maps.get('stock.package',{}).get(rid(x['result_package_id']),False))
    expected[key]+=self.effective_qty(x)
  for x in rows:
   if x['quantity']>1e-8:
    primary_finished={mm[i] for e in events if e['kind']=='mo' for i in self.mos[e['source']]['move_finished_ids'] if i in mm and rid(self.mm[i]['product_id'])==rid(self.mos[e['source']]['product_id'])}
    require(x['picked'] or rid(x['move_id']) in primary_finished,'Unpicked extra quantity before completion')
    key=tuple(rid(x[k]) for k in ['move_id','product_id','product_uom_id','location_id','location_dest_id','lot_id','package_id','result_package_id']);actual[key]+=x['quantity']
  require(set(expected)==set(actual) and all(abs(expected[k]-actual[k])<1e-6 for k in expected),'Prepared detail differs from source')
  return mids,rows
 def prepare_validation(self):
  require(self.j['phases'].get('details'),'Preparation incomplete')
  self.uoms=index(self.b.search_read('uom.uom',[],['name','factor','rounding']))
  precision=self.b.search_read('decimal.precision',[['name','=','Product Unit']],['digits'])[0]['digits']
  self.precision_blocked_mo=set()
  for x in self.ml.values():
   u=self.uoms[self.maps['uom.uom'][rid(x['product_uom_id'])]]
   if abs(x['qty_done']-round(x['qty_done'],precision))>1e-8 or abs(x['qty_done']/u['rounding']-round(x['qty_done']/u['rounding']))>1e-6:
    self.precision_blocked_mo.add(rid(self.mm[rid(x['move_id'])]['raw_material_production_id']) or rid(self.mm[rid(x['move_id'])]['production_id']))
  self.j['precision_blocked_MO']=sorted(self.precision_blocked_mo)
  self.auto_invoice_orders=set()
  fields=self.b.call('sale.order','fields_get',[],{'attributes':['type']})
  if 'auto_workflow_process_id' in fields:
   orders=self.b.read('sale.order',list(self.maps['sale.order'].values()),['auto_workflow_process_id'])
   workflow_ids={rid(x['auto_workflow_process_id']) for x in orders if x['auto_workflow_process_id']}
   schema=fields['auto_workflow_process_id'];model=self.b.call('sale.order','fields_get',[['auto_workflow_process_id']],{'attributes':['relation']})['auto_workflow_process_id']['relation']
   workflows=index(self.b.read(model,workflow_ids,['create_invoice']))
   self.auto_invoice_orders={x['id'] for x in orders if x['auto_workflow_process_id'] and workflows[rid(x['auto_workflow_process_id'])]['create_invoice']}
  target_sol=index(self.sb['sol']);self.auto_invoice_picks={rid(t['picking_id']) for t in self.sb['moves'] if t['sale_line_id'] and rid(target_sol[rid(t['sale_line_id'])]['order_id']) in self.auto_invoice_orders}
  self.j['auto_invoice_orders_blocked']=sorted(self.auto_invoice_orders)
  if 'baseline_invoice_ids' not in self.j:self.j['baseline_invoice_ids']=self.b.call('account.move','search',[[['company_id','=',1],['move_type','in',['out_invoice','out_refund','in_invoice','in_refund']]]])
  self.persist()
 def complete(self,retry_pending=False,only_event_keys=None):
  self.prepare_validation();events=[]
  for s,t in self.maps['stock.picking'].items():
   p=self.sp[s]
   if p['state']=='done':events.append({'kind':'picking','source':s,'target':t,'date':p['date_done'],'reference':p['name']})
  for s,t in self.maps['mrp.production'].items():events.append({'kind':'mo','source':s,'target':t,'date':self.mos[s]['date_finished'],'reference':self.mos[s]['name']})
  events.sort(key=lambda x:(x['date'],x['source']));done=set(self.j.get('completed_events',[]));results=self.j.setdefault('event_results',{})
  balances=self.ledger(self.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','package_id','owner_id','quantity']))
  # Historical predecessor events must already have completed; no borrowing future receipts.
  mm=self.maps['stock.move'];reverse={t:s for s,t in mm.items()};targetstates={x['id']:x['state'] for x in self.b.read('stock.move',list(mm.values()),['state'])}
  picking_source_moves=defaultdict(set)
  for m in self.sm.values():picking_source_moves[rid(m['picking_id'])].add(m['id'])
  def dependencies(e):
   mids={rid(x['move_id']) for x in self.expected(e)}
   deps=[]
   for i in mids:
    source=self.sm.get(i) or self.mm[i]
    for j in source['move_orig_ids']:
     if j not in mm or targetstates.get(mm[j]) in ['done','cancel']:continue
     predecessor=self.sm.get(j) or self.mm[j]
     if predecessor['state']!='done' or predecessor['date']>source['date']:
      reason='Source predecessor not done' if predecessor['state']!='done' else 'Source predecessor dated after consumption'
      self.j.setdefault('ignored_historical_predecessor_links',{})[str(i)+':'+str(j)]={'source_move':i,'predecessor':j,'source_date':source['date'],'predecessor_date':predecessor['date'],'predecessor_state':predecessor['state'],'reason':reason,'quantity_lot_location_gate_still_required':True}
      continue
     deps.append(j)
   return sorted(set(deps))
  pending=[]
  def flush():
   nonlocal pending,balances
   if not pending:return
   kind=pending[0]['kind'];ids=[e['target'] for e in pending];mids,rows=self.verify_details(pending)
   context={'skip_backorder':True,'skip_redirection':True,'tracking_disable':True}
   if kind=='picking':context['picking_ids_not_to_backorder']=ids
   model='stock.picking' if kind=='picking' else 'mrp.production'
   before_states=self.b.read(model,ids,['state'])
   active=[x['id'] for x in before_states if x['state']!='done']
   if active:
    result=self.mutate(model,'button_validate' if kind=='picking' else 'button_mark_done',[active],{'context':context})
    if isinstance(result,dict) and result.get('res_model')=='expiry.picking.confirmation':
     self.j.setdefault('historical_expiry_acknowledgements',[]).append({'sources':[e['source'] for e in pending],'kind':kind,'warning':result});self.persist()
     ctx=result.get('context',{});values={'lot_ids':ctx.get('default_lot_ids',[]),'production_ids' if kind=='mo' else 'picking_ids':[(6,0,active)]}
     wizard=self.mutate('expiry.picking.confirmation','create',[values],{'context':ctx})
     self.mutate('expiry.picking.confirmation','confirm_produce' if kind=='mo' else 'process',[[wizard]],{'context':ctx})
   states=self.b.read(model,ids,['state','company_id']);require(all(x['state']=='done' and rid(x['company_id'])==1 for x in states),'Completion returned a wizard or unexpected state')
   # Restore both document and stock movement dates after standard Odoo completion.
   if kind=='mo':self.matrix(model,['.id','date_finished'],[[e['target'],e['date']] for e in pending])
   else:self.matrix(model,['.id','date_done','scheduled_date'],[[e['target'],e['date'],self.sp[e['source']]['scheduled_date']] for e in pending])
   self.matrix('stock.move',['.id','date'],[[t,(self.sm.get(s) or self.mm[s])['date']] for t in mids for s in [reverse[t]]])
   dates={self.maps['stock.move.line'][x['id']]:x['date'] for e in pending for x in self.expected(e)}
   self.matrix('stock.move.line',['.id','date'],[[t,dates[t]] for t in dates])
   after=self.b.read('stock.move',list(mids),['state']);targetstates.update({x['id']:x['state'] for x in after})
   for e in pending:
    key=self.eventkey(e);done.add(key);results[key]={'status':'done',**e}
   self.j['completed_events']=sorted(done);self.persist()
   print(json.dumps({'completed':len(done),'total':len(events),'through':pending[-1]['date'],'kind':kind}),flush=True)
   pending=[]
   affected={rid(x['product_id']) for x in rows}
   refreshed=self.ledger(self.b.search_read('stock.quant',[['company_id','=',1],['product_id','in',sorted(affected)]],['product_id','location_id','lot_id','package_id','owner_id','quantity']))
   for k in list(balances):
    if k[0] in affected:balances.pop(k)
   balances.update(refreshed)
  def priority(e):
   if e['kind']=='mo':return 1
   p=self.sp[e['source']];src=self.locations[self.maps['stock.location'][rid(p['location_id'])]]['usage'];dest=self.locations[self.maps['stock.location'][rid(p['location_dest_id'])]]['usage']
   return 0 if src in ['supplier','customer'] and dest in ['internal','transit'] else 2 if dest in ['internal','transit'] else 3
  byday=defaultdict(list)
  def business_day(e):return datetime.strptime(e['date'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
  if 'processed_business_days' not in self.j:
   latest=max((business_day(e) for e in events if self.eventkey(e) in done),default='')
   self.j['processed_business_days']=sorted({business_day(e) for e in events if business_day(e)<latest})
  processed=set(self.j['processed_business_days'])
  for e in events:
   if self.eventkey(e) not in done:
    # Source user timezone was read as Asia/Singapore (UTC+08 throughout 2026).
    # This offset is used only for the day grouping, never added to stored dates.
    day=business_day(e)
    if (retry_pending or day not in processed) and (only_event_keys is None or self.eventkey(e) in only_event_keys):byday[day].append(e)
  stored={x['id']:x['is_storable'] for x in self.b.read('product.product',list(self.product),['is_storable'])}
  def historical_balance(cutoff,selected_keys=()):
   result=self.ledger(self.j['baseline_quants'])
   for correction in self.j.get('opening_stock_corrections',[]):
    if correction['status']=='verified':
     for k,delta in correction['deltas']:result[tuple(k)]+=delta
   for receipt in self.j.get('supporting_source_transfers',[]):
    if receipt['status']=='verified' and receipt['date']<=cutoff:
     for k,delta in receipt['deltas']:result[tuple(k)]+=delta
   for receipt in self.j.get('standalone_source_receipts',[]):
    if receipt['status']=='verified' and receipt['date']<=cutoff:
     for k,delta in receipt['deltas']:result[tuple(k)]+=delta
   for correction in self.j.get('opening_package_reclassifications',[]):
    if correction['status']=='verified':
     for k,delta in correction['deltas']:result[tuple(k)]+=delta
   for adjustment in self.j.get('supplementary_inventory_adjustments',[]):
    if adjustment['date']<=cutoff:
     for k,delta in adjustment['deltas']:result[tuple(k)]+=delta
   for adjustment in self.j.get('temporary_negative_stock_adjustments',[]):
    if adjustment['status']=='verified' and adjustment['date']<=cutoff:
     for k,delta in adjustment['deltas']:result[tuple(k)]+=delta
   for event in events:
    if self.eventkey(event) in done:
     for line in self.expected(event):
      source_move=self.sm.get(rid(line['move_id'])) or self.mm[rid(line['move_id'])]
      if source_move['date']<=cutoff:
       result[self.quantkey(line)]-=self.qty(line);result[self.quantkey(line,True)]+=self.qty(line)
   # An earlier blocked document still owns its source stock. Do not let a
   # later document consume that allocation just because another SKU blocked it.
   for earlier in events:
    if earlier['date']<cutoff and self.eventkey(earlier) not in done and self.eventkey(earlier) not in selected_keys:
     for k,q in consumption(earlier).items():result[k]-=q
   return result
  def consumption(e):
   d=defaultdict(float)
   for x in self.expected(e):
    if stored.get(self.quantkey(x)[0],True) and targetstates.get(mm[rid(x['move_id'])])!='done' and self.locations[self.quantkey(x)[1]]['usage'] in ['internal','transit']:d[self.quantkey(x)]+=self.qty(x)
   return d
  self.j['completion_schedule']='Business date Asia/Singapore; independent batches only, providers before consumers within each day.'
  for day,dayevents in sorted(byday.items()):
   remaining=sorted(dayevents,key=lambda e:(priority(e),e['date'],e['source']))
   while remaining:
    pending=[];available=defaultdict(float,balances);historical_used=defaultdict(float)
    for e in remaining:
     key=self.eventkey(e)
     if key in self.j.get('native_validation_exceptions',{}):
      results[key]={'status':'blocked_native_validation','reason':self.j['native_validation_exceptions'][key],**e};continue
     if e['kind']=='picking' and e['target'] in self.auto_invoice_picks:results[key]={'status':'blocked_auto_invoice',**e};continue
     if e['kind']=='mo' and e['source'] in self.precision_blocked_mo and not self.j.get('approved_two_decimal_rounding'):results[key]={'status':'blocked_precision',**e};continue
     deps=dependencies(e)
     if deps:results[key]={'status':'blocked_predecessor','source_moves':deps,**e};continue
     historical=historical_balance(e['date'],{self.eventkey(x) for x in pending}) if retry_pending else None
     need=consumption(e);allowed_history_keys=set();source_allowances=self.j.get('historical_source_negative_allowances',{})
     for k in need:
      matching=[x for x in self.expected(e) if self.quantkey(x)==k and targetstates.get(mm[rid(x['move_id'])])!='done']
      if matching and all(str(rid(x['move_id'])) in source_allowances for x in matching):allowed_history_keys.add(k)
     shortage=[{'key':k,'available':available[k],'historical_available':historical[k]-historical_used[k] if historical is not None else None,'required':q} for k,q in need.items() if available[k]-q<-1e-6 or (historical is not None and k not in allowed_history_keys and historical[k]-historical_used[k]-q<-1e-6)]
     if shortage:results[key]={'status':'blocked_stock','shortage':shortage,**e};continue
     if pending and (e['kind']!=pending[0]['kind'] or priority(e)!=priority(pending[0])):continue
     for k,q in need.items():
      available[k]-=q
      if historical is not None:historical_used[k]+=q
     pending.append(e)
     if len(pending)>=50:break
    if not pending:break
    chosen={self.eventkey(e) for e in pending};flush();remaining=[e for e in remaining if self.eventkey(e) not in chosen]
   print(json.dumps({'day_finished':day,'completed':len(done),'blocked_this_day':len(remaining)}),flush=True)
   processed.add(day);self.j['processed_business_days']=sorted(processed)
   self.persist()
  self.j['phases']['completion_pass']=True;self.persist();print(json.dumps({'result_counts':dict(Counter(x['status'] for x in results.values()))}),flush=True)
 def audit(self, coverage_report=None):
  self.prepare_validation();mm=self.maps['stock.move'];pm=self.maps['stock.picking'];mom=self.maps.get('mrp.production',{})
  targetp=index(self.b.read('stock.picking',list(pm.values()),['name','state','company_id','date_done','move_ids','backorder_id','location_id','location_dest_id']))
  targetmo=index(self.b.read('mrp.production',list(mom.values()),['name','state','company_id','date_start','date_finished','x_studio_reference_no','origin','product_id','product_qty','move_raw_ids','move_finished_ids']))
  tm=index(self.b.read('stock.move',list(mm.values()),['state','company_id','product_id','product_uom','product_uom_qty','quantity','location_id','location_dest_id','picking_id','date','move_line_ids']))
  lines=self.b.read('stock.move.line',[i for m in tm.values() for i in m['move_line_ids']],['move_id','product_id','product_uom_id','location_id','location_dest_id','lot_id','quantity','date','state','package_id','result_package_id','picked'])
  bymove=defaultdict(list)
  for x in lines:bymove[rid(x['move_id'])].append(x)
  comparisons=[]
  for s,t in mm.items():
   src=self.sm.get(s) or self.mm[s];actual=tm[t];expected_lines=[x for x in (self.sl if s in self.sm else self.ml).values() if rid(x['move_id'])==s and x['qty_done']>0]
   expected=defaultdict(float);got=defaultdict(float)
   for x in expected_lines:expected[(self.maps['product.product'][rid(x['product_id'])],self.maps['uom.uom'][rid(x['product_uom_id'])],self.maps['stock.location'][rid(x['location_id'])],self.maps['stock.location'][rid(x['location_dest_id'])],self.maps['stock.lot'].get(rid(x['lot_id']),False))]+=x['qty_done']
   for x in bymove[t]:
    if x['quantity']>1e-8:got[tuple(rid(x[k]) for k in ['product_id','product_uom_id','location_id','location_dest_id','lot_id'])]+=x['quantity']
   qtymatch=set(expected)==set(got) and all(abs(expected[k]-got[k])<1e-6 for k in expected)
   date_match=src['date']==actual['date'] if actual['state']=='done' else None
   rounded=defaultdict(float)
   for x in expected_lines:rounded[(self.maps['product.product'][rid(x['product_id'])],self.maps['uom.uom'][rid(x['product_uom_id'])],self.maps['stock.location'][rid(x['location_id'])],self.maps['stock.location'][rid(x['location_dest_id'])],self.maps['stock.lot'].get(rid(x['lot_id']),False))]+=self.effective_qty(x)
   accepted_rounding=not qtymatch and bool(self.j.get('approved_two_decimal_rounding')) and set(rounded)==set(got) and all(abs(rounded[k]-got[k])<1e-6 for k in rounded)
   comparisons.append({'source_move':s,'target_move':t,'source_state':src['state'],'target_state':actual['state'],'details_match':qtymatch,'pending_reservation_only':not expected and bool(got) and src['state']!='done' and actual['state']!='done' and all(not x['picked'] for x in bymove[t]),'approved_rounding_difference':accepted_rounding,'date_match':date_match,'expected':[{'key':k,'qty':v} for k,v in expected.items()],'actual':[{'key':k,'qty':v} for k,v in got.items()]})
  mo_compare=[]
  for s,t in mom.items():
   src=self.mos[s];target=targetmo[t]
   mo_compare.append({'source_id':s,'target_id':t,'name':src['name'],'source_reference':src.get('x_studio_reference_no') or False,'target_reference':target['x_studio_reference_no'],'reference_match':(src.get('x_studio_reference_no') or False)==target['x_studio_reference_no'],'state':target['state'],'date_match':target['date_finished']==src['date_finished'] if target['state']=='done' else None})
  currentq=self.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','owner_id','package_id','quantity','reserved_quantity']);baseline=self.ledger(self.j['baseline_quants']);expected=defaultdict(float,baseline)
  for key,event in self.j.get('event_results',{}).items():
   if event['status']=='done':
    for k,delta in self.changes(event).items():expected[k]+=delta
  for adjustment in self.j.get('supplementary_inventory_adjustments',[]):
   for k,delta in adjustment['deltas']:expected[tuple(k)]+=delta
  for correction in self.j.get('opening_package_reclassifications',[]):
   if correction['status']=='verified':
    for k,delta in correction['deltas']:expected[tuple(k)]+=delta
  for adjustment in self.j.get('temporary_negative_stock_adjustments',[]):
   if adjustment['status']=='verified':
    for k,delta in adjustment['deltas']:expected[tuple(k)]+=delta
  for receipt in self.j.get('standalone_source_receipts',[]):
   if receipt['status']=='verified':
    for k,delta in receipt['deltas']:expected[tuple(k)]+=delta
  for receipt in self.j.get('supporting_source_transfers',[]):
   if receipt['status']=='verified':
    for k,delta in receipt['deltas']:expected[tuple(k)]+=delta
  for correction in self.j.get('opening_stock_corrections',[]):
   if correction['status']=='verified':
    for k,delta in correction['deltas']:expected[tuple(k)]+=delta
  actual=self.ledger(currentq);ledger_diffs=[{'key':k,'expected':expected[k],'actual':actual[k],'delta':actual[k]-expected[k]} for k in set(expected)|set(actual) if abs(expected[k]-actual[k])>1e-6]
  stored={x['id']:x['is_storable'] for x in self.b.read('product.product',list(self.product),['is_storable'])}
  virtual_diffs=[x for x in ledger_diffs if self.locations[x['key'][1]]['usage'] not in ['internal','transit'] or not stored.get(x['key'][0],True)]
  ledger_diffs=[x for x in ledger_diffs if x not in virtual_diffs]
  currentprod=self.b.read('product.product',[x['id'] for x in self.j['baseline_products']],['name','default_code','barcode','tracking','uom_id','packing_ratio','active']);require(currentprod==self.j['baseline_products'],'Product master changed')
  invoiceids=self.b.call('account.move','search',[[['company_id','=',1],['move_type','in',['out_invoice','out_refund','in_invoice','in_refund']]]]);require(set(invoiceids)==set(self.j['baseline_invoice_ids']),'Unexpected invoice/bill creation')
  report={'database':self.b.db,'company_id':1,'summary':{'pickings_prepared':len(pm),'picking_states':dict(Counter(x['state'] for x in targetp.values())),'MO_prepared':len(mom),'MO_states':dict(Counter(x['state'] for x in targetmo.values())),'moves_prepared':len(mm),'moves_details_match':sum(x['details_match'] for x in comparisons),'approved_rounding_differences':sum(x['approved_rounding_difference'] for x in comparisons),'done_move_date_mismatches':sum(x['date_match'] is False for x in comparisons),'references_match':all(x['reference_match'] for x in mo_compare),'ledger_differences':len(ledger_diffs),'product_masters_preserved':True,'no_invoice_or_bill_created':True},'pickings':[{'source':s,'source_name':self.sp[s]['name'],'source_state':self.sp[s]['state'],'source_date':self.sp[s]['date_done'],'target':targetp[t]} for s,t in pm.items()], 'MO':mo_compare,'moves':comparisons,'ledger_differences':ledger_diffs,'event_results':self.j.get('event_results',{}),'excluded_pickings':self.j['blocked_source_pickings'],'excluded_MO':self.j['blocked_mo'],'mapping_exceptions':self.p['exceptions']+self.p['mo_exceptions']}
  report['coverage_gate']=acceptance_gate(coverage_report or OUT/'july-other-stock-coverage.json')
  report['summary']['full_company_move_coverage_ready']=report['coverage_gate']['full_acceptance_ready']
  report['acceptance_scope']='Mapped migration records only; full-company inventory acceptance requires independent stock reconciliation and a fresh exhaustive move scan.'
  report['supplementary_inventory_adjustments']=self.j.get('supplementary_inventory_adjustments',[]);report['summary']['supplementary_inventory_adjustments']=len(report['supplementary_inventory_adjustments']);report['summary']['pending_reservation_only_moves']=sum(x['pending_reservation_only'] for x in comparisons);report['excluded_virtual_or_nonstored_ledger_differences']=virtual_diffs;report['ledger_scope']='Internal/transit locations for is_storable products only; Odoo does not maintain physical quants for external locations or nonstored products.';H['save'](OUT/'stock-reconciliation-report.json',report);print(json.dumps(report['summary'],ensure_ascii=False,indent=2),flush=True)
  table=[]
  for key,value in report['summary'].items():table.append('<tr><td>'+html.escape(key)+'</td><td>'+html.escape(str(value))+'</td></tr>')
  events=''.join('<tr><td>'+html.escape(str(x.get('reference','')))+ '</td><td>'+html.escape(x['kind'])+'</td><td>'+html.escape(x['date'])+'</td><td>'+html.escape(x['status'])+'</td></tr>' for x in report['event_results'].values())
  (OUT/'stock-reconciliation-report.html').write_text('<!doctype html><meta charset="utf-8"><title>Pao Yeang – đối chiếu kho</title><style>body{font:15px Arial;margin:32px}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:7px}th{background:#edf5fa}</style><h1>Pao Yeang – đối chiếu chuyển kho v14 → v19 staging</h1><p>Đối chiếu số lượng, lot/serial và ngày lịch sử. Valuation không dùng làm tiêu chí khớp.</p><table>'+''.join(table)+'</table><h2>Chứng từ hoàn tất và ngoại lệ</h2><table><tr><th>Chứng từ v14</th><th>Loại</th><th>Ngày UTC</th><th>Kết quả</th></tr>'+events+'</table><p>Chi tiết dòng, lot, số lượng và chênh lệch tồn: stock-reconciliation-report.json</p>',encoding='utf8')
def main():
 p=argparse.ArgumentParser();p.add_argument('--complete',action='store_true');p.add_argument('--audit',action='store_true');p.add_argument('--coverage-report',type=Path);p.add_argument('--retry-pending',action='store_true');p.add_argument('--event-keys-file');p.add_argument('--accept-two-decimal-rounding',action='store_true');args=p.parse_args();m=Completion()
 if args.accept_two_decimal_rounding:m.j['approved_two_decimal_rounding']=True;m.j['rounding_authorization']='Bruce: giữ cấu hình và vẫn hoàn tất các MO này';m.persist()
 try:
  if args.complete:m.complete(retry_pending=args.retry_pending,only_event_keys=set(json.loads(Path(args.event_keys_file).read_text(encoding='utf8'))) if args.event_keys_file else None)
  if args.audit:m.audit(args.coverage_report)
 except Exception:m.j['last_error']=traceback.format_exc();m.persist();raise
if __name__=='__main__':main()
