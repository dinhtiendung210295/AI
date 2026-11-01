"""Company-1 historical stock migration, staging only; explicit journal, no RPC retries.

Preparation reconstructs existing source-confirmed transaction moves without running
procurement again. Completion always uses Odoo button_validate/button_mark_done.
Missing mappings/stock are reported, never replaced with invented master data.
"""
import argparse,copy,json,runpy,socket,traceback,time
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
require,save,rid=H['require'],H['save'],H['rid']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def index(rows):return {x['id']:x for x in rows}
def chunks(rows,n=100):
 for i in range(0,len(rows),n):yield rows[i:i+n]
class Migration:
 def __init__(self):
  socket.setdefaulttimeout(120)
  self.a=H['Reader'](ROOT/'mcp-server-odoo/envs/v14-prod/.env');self.b=H['Reader'](ROOT/'mcp-server-odoo/envs/v19-staging/.env')
  require((self.a.url,self.a.db)==('http://175.145.85.151','paoyeang_live'),'Wrong source')
  require((self.b.url,self.b.db)==('https://py-staging.odoo.com','py19-staging-39654560'),'Wrong target')
  require(self.b.read('res.company',[1],['name'])[0]['name']=='PAO YEANG SDN BHD','Wrong company')
  self.sa=load('v14-prod-snapshot.json');self.sb=load('v19-staging-snapshot.json');self.mo=load('mo-details.json');self.p=load('execution-manifest.json')
  self.maps={m:{int(s):t for s,t in v.items()} for m,v in self.p['maps'].items()}
  self.sm=index(self.sa['moves']+self.sa['chain_moves']);self.sp=index(self.sa['pickings']+self.sa['chain_pickings']);self.sl=index(self.sa['move_lines']+self.sa['chain_move_lines'])
  self.mm=index(self.mo['moves']);self.ml=index(self.mo['lines']);self.mos=index(self.mo['mo'])
  self.product=index(self.p['target_products']);self.locations=index(self.sb['locations'])
  self.path=OUT/'execution-journal.json'
  if self.path.exists():self.j=load('execution-journal.json')
  else:self.j={'database':self.b.db,'company_id':1,'started_utc':datetime.now(timezone.utc).isoformat(),'operations':[],'maps':{},'phases':{},'exceptions':[]}
  for model,m in self.j['maps'].items():self.maps[model]={int(s):t for s,t in m.items()}
  missing_locations=set(self.maps['stock.location'].values())-set(self.locations)
  if missing_locations:self.locations.update(index(self.b.read('stock.location',list(missing_locations),['name','usage','company_id','location_id'])))
  self.blocked_source=set();self.blocked_target=set();self._blocks()
 def _blocks(self):
  source_sol=index(self.sa['sol']);target_sol=index(self.sb['sol']);source_orders=set();target_orders=set()
  for e in self.p['exceptions']:
   if e['type']=='missing_mapping':
    if e.get('picking_id'):self.blocked_source.add(e['picking_id'])
    if e.get('move_id'):self.blocked_source.add(rid(self.sm[e['move_id']]['picking_id']))
   if e['type']=='unmatched_existing_move':
    t=index(self.sb['moves'])[e['target']]
    if t['sale_line_id']:target_orders.add(rid(target_sol[rid(t['sale_line_id'])]['order_id']))
  for line in self.sl.values():
   if line['qty_done']>0 and not line['lot_id'] and self.product[self.maps['product.product'][rid(line['product_id'])]]['tracking']!='none':
    self.blocked_source.add(rid(line['picking_id']))
  inverse={v:k for k,v in self.maps['sale.order'].items()}
  source_orders.update(inverse[t] for t in target_orders)
  for m in self.sm.values():
   if m['sale_line_id'] and rid(source_sol.get(rid(m['sale_line_id']),{}).get('order_id')) in source_orders:self.blocked_source.add(rid(m['picking_id']))
  # Keep an entire linked transaction chain out if one location has no mapping.
  for _ in range(12):
   before=len(self.blocked_source)
   for m in self.sm.values():
    if rid(m['picking_id']) in self.blocked_source:
     for i in m['move_orig_ids']+m['move_dest_ids']:
      if i in self.sm:self.blocked_source.add(rid(self.sm[i]['picking_id']))
   if len(self.blocked_source)==before:break
  for t in self.sb['moves']:
   if t['sale_line_id'] and rid(target_sol[rid(t['sale_line_id'])]['order_id']) in target_orders:self.blocked_target.add(rid(t['picking_id']))
  for sid,tid in self.p['reuse_moves'].items():
   if rid(self.sm[int(sid)]['picking_id']) in self.blocked_source:self.blocked_target.add(rid(index(self.sb['moves'])[tid]['picking_id']))
  for sid,tid in self.p['reuse_moves'].items():
   if rid(index(self.sb['moves'])[tid]['picking_id']) in self.blocked_target:self.blocked_source.add(rid(self.sm[int(sid)]['picking_id']))
  for _ in range(12):
   before=(len(self.blocked_source),len(self.blocked_target))
   for m in self.sm.values():
    if rid(m['picking_id']) in self.blocked_source:
     for i in m['move_orig_ids']+m['move_dest_ids']:
      if i in self.sm:self.blocked_source.add(rid(self.sm[i]['picking_id']))
   for sid,tid in self.p['reuse_moves'].items():
    sourcepick=rid(self.sm[int(sid)]['picking_id']);targetpick=rid(index(self.sb['moves'])[tid]['picking_id'])
    if sourcepick in self.blocked_source:self.blocked_target.add(targetpick)
    if targetpick in self.blocked_target:self.blocked_source.add(sourcepick)
   if before==(len(self.blocked_source),len(self.blocked_target)):break
  self.j['blocked_source_pickings']=sorted(self.blocked_source);self.j['blocked_target_pickings']=sorted(self.blocked_target);self.j['blocked_mo']=self.p['blocked_mo']
 def persist(self):
  self.j['maps']={m:v for m,v in self.maps.items() if m in ['stock.lot','stock.package','stock.picking','stock.move','stock.move.line','mrp.production']}
  # Windows readers can briefly deny replacing an open file; retry only the local
  # atomic journal save, never an Odoo RPC operation.
  for attempt in range(30):
   try:save(self.path,self.j);return
   except PermissionError:
    if attempt==29:raise
    time.sleep(0.1)
 def mutate(self,model,method,args,kwargs=None):
  kwargs=copy.deepcopy(kwargs or {});kwargs['context']={'tracking_disable':True,'mail_notrack':True,'mail_create_nolog':True,'mail_create_nosubscribe':True,**kwargs.get('context',{})}
  op={'model':model,'method':method,'args':args,'kwargs':kwargs,'status':'intent','utc':datetime.now(timezone.utc).isoformat()}
  self.j['operations'].append(op);self.persist()
  try:
   result=self.b.call(model,method,args,kwargs or {})
   if method=='load':require(bool(result.get('ids')) and not any(x.get('type')=='error' for x in result.get('messages',[])),f'Import failed: {result}')
   op['status']='returned';op['result']=result;self.persist();return result
  except Exception as e:
   if method=='do_unreserve' and 'cannot marshal None' in str(e):
    rows=self.b.search_read('stock.move',[['picking_id','in',args[0]],['company_id','=',1]],['quantity','move_line_ids','state'])
    require(all(abs(x['quantity'])<1e-6 and not x['move_line_ids'] and x['state'] not in ['done','cancel'] for x in rows),'Unreserve result uncertain')
    op['status']='verified_after_none_response';op['result']=True;self.persist();return True
   op['status']='uncertain_or_failed';op['error']=str(e);self.persist();raise
 def attach(self,model,pairs):
  # Attach unique external IDs only after IDs are known from a successful RPC.
  existing=H['external'](self.b,model);values=[]
  for s,t in pairs:
   require(existing.get(s,t)==t,'External mapping conflict')
   if s not in existing:values.append({'module':'pysb_v14','name':model.replace('.','_')+'_'+str(s),'model':model,'res_id':t,'noupdate':True})
  for batch in chunks(values,300):self.mutate('ir.model.data','create',[batch])
 def matrix(self,model,fields,rows,batch_size=100):
  for batch in chunks(rows,batch_size):
   data=[]
   for row in batch:
    data.append([('True' if v is True else '' if v is False or v is None else str(v)) for v in row])
   self.mutate(model,'load',[fields,data],{'context':{'tz':'UTC','tracking_disable':True,'mail_create_nolog':True,'mail_create_nosubscribe':True}})
  print(json.dumps({'updated':model,'rows':len(rows)}),flush=True)
 def preflight(self):
  if self.j['phases'].get('preflight'):return
  require(not H['external'](self.b,'stock.move'),'Unexpected previous stock migration')
  current=self.b.read('stock.move',[x['id'] for x in self.sb['moves']],['state','product_id','product_uom_qty','location_id','location_dest_id','picking_id'])
  old=index(self.sb['moves'])
  require(all(all(x[k]==old[x['id']][k] for k in x if k!='id') for x in current),'Target stock changed since snapshot')
  require(not self.b.search_read('mrp.production',[['company_id','=',1]],['id']),'Existing target MO needs review')
  self.j['baseline_quants']=self.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','owner_id','package_id','quantity','reserved_quantity'])
  self.j['baseline_products']=self.b.read('product.product',list(self.product),['name','default_code','barcode','tracking','uom_id','packing_ratio','active'])
  # Freeze source execution data again immediately before first mutation.
  for model,rows,fields in [('stock.picking',list(self.sp.values()),['company_id','state','date_done','location_id','location_dest_id']),('stock.move',list(self.sm.values())+list(self.mm.values()),['company_id','state','product_id','product_uom','product_uom_qty','location_id','location_dest_id','move_line_ids']),('stock.move.line',list(self.sl.values())+list(self.ml.values()),['company_id','product_id','product_uom_id','qty_done','lot_id','location_id','location_dest_id'])]:
   baseline=index(rows);fresh=self.a.read(model,list(baseline),fields)
   require(len(fresh)==len(baseline) and all(all(x[k]==baseline[x['id']][k] for k in fields) for x in fresh),'Source changed: '+model)
   print('fresh source checked',model,len(fresh),flush=True)
  self.j['phases']['preflight']=True;self.persist()
 def prepare_lots(self):
  if self.j['phases'].get('lots'):return
  current=self.b.search_read('stock.lot',[['company_id','=',1]],['name','product_id','company_id']);lookup=defaultdict(list)
  for x in current:lookup[rid(x['product_id']),x['name']].append(x['id'])
  mapping=self.maps.setdefault('stock.lot',{});pending=[]
  for x in self.p['lot_plan']:
   require(x['status']!='exception','Unresolved lot mapping')
   key=(x['product_id'],x['name']);hits=lookup[key];require(len(hits)<=1,'Duplicate target lot')
   if hits:mapping[x['source_id']]=hits[0]
   elif x['source_id'] not in mapping:pending.append(x)
  for batch in chunks(pending,100):
   ids=self.mutate('stock.lot','create',[[{'name':x['name'],'product_id':x['product_id'],'company_id':1} for x in batch]])
   require(len(ids)==len(batch),'Missing created lots')
   mapping.update({x['source_id']:t for x,t in zip(batch,ids)});self.persist()
  self.attach('stock.lot',list(mapping.items()))
  self.j['phases']['lots']=True;self.persist();print('lots ready',len(mapping),flush=True)
 def prepare_packages(self):
  if self.j['phases'].get('packages'):return
  source=load('v14-prod-dependencies.json')['packages'];current=self.b.search_read('stock.package',[['company_id','=',1]],['name']);mapping=self.maps.setdefault('stock.package',{})
  for x in source:
   hits=[t['id'] for t in current if t['name']==x['name']];require(len(hits)<=1,'Ambiguous package')
   mapping[x['id']]=hits[0] if hits else self.mutate('stock.package','create',[{'name':x['name'],'company_id':1}])
  self.attach('stock.package',list(mapping.items()));self.j['phases']['packages']=True;self.persist()
 def mv(self,m,*,picking=None,mo=None,kind=None,state='confirmed'):
  v={'company_id':1,'product_id':self.maps['product.product'][rid(m['product_id'])],'product_uom':self.maps['uom.uom'][rid(m['product_uom'])],
     'product_uom_qty':m['product_uom_qty'],'location_id':self.maps['stock.location'][rid(m['location_id'])],'location_dest_id':self.maps['stock.location'][rid(m['location_dest_id'])],
     'date':m['date'],'state':state,'procure_method':'make_to_stock','propagate_cancel':False,'rule_id':False}
  if 'location_final_id' in self.sb['schemas']['stock.move']:v['location_final_id']=v['location_dest_id']
  if 'name' in self.sb['schemas']['stock.move']:v['name']=m.get('name') or m['product_id'][1]
  if picking:v['picking_id']=picking
  if mo:v['raw_material_production_id' if kind=='raw' else 'production_id']=mo
  for k,model in [('sale_line_id','sale.order.line'),('purchase_line_id','purchase.order.line')]:v[k]=self.maps[model].get(rid(m.get(k)),False)
  flags=index(self.mo['transfer_move_flags']).get(m['id'],m)
  if 'to_refund' in self.sb['schemas']['stock.move']:v['to_refund']=flags.get('to_refund',False)
  return v
 def prepare_transfers(self):
  if self.j['phases'].get('transfers'):return
  require(not self.j['phases'].get('transfer_preparation_started') or self.j.pop('reviewed_transfer_resume',False),'Interrupted preparation must be reviewed before resume')
  self.j['phases']['transfer_preparation_started']=True;self.persist()
  picks=[p for p in self.sp.values() if p['id'] not in self.blocked_source]
  mids={m['id'] for m in self.sm.values() if rid(m['picking_id']) not in self.blocked_source}
  reuse={int(s):t for s,t in self.p['reuse_moves'].items() if int(s) in mids and rid(index(self.sb['moves'])[t]['picking_id']) not in self.blocked_target}
  existing=[p['id'] for p in self.sb['pickings'] if p['id'] not in self.blocked_target]
  already=set(self.j.get('unreserved_picking_ids',[]))
  for batch in chunks([i for i in existing if i not in already],100):
   self.mutate('stock.picking','do_unreserve',[batch]);already.update(batch);self.j['unreserved_picking_ids']=sorted(already);self.persist()
  # Remove only preexisting reserved/detailed operations in our uncompleted target scope.
  lines=self.b.search_read('stock.move.line',[['picking_id','in',existing],['company_id','=',1]],['state'])
  require(all(x['state'] not in ['done','cancel'] for x in lines),'Completed target operations present')
  for batch in chunks([x['id'] for x in lines],500):self.mutate('stock.move.line','unlink',[batch])
  tm=index(self.sb['moves']);votes=defaultdict(Counter)
  for s,t in reuse.items():votes[rid(tm[t]['picking_id'])][rid(self.sm[s]['picking_id'])]+=1
  pm=self.maps.setdefault('stock.picking',{});used=set()
  for tid,c in votes.items():
   choices=sorted(c,key=lambda s:(-c[s],s))
   for sid in choices:
    if sid not in used:pm[sid]=tid;used.add(sid);break
  unmatched=[t for t in existing if t not in pm.values()]
  require(not unmatched,'Target picking without source counterpart: '+str(unmatched))
  new=[p for p in picks if p['id'] not in pm]
  def pv(p):
   return {'company_id':1,'picking_type_id':self.maps['stock.picking.type'][rid(p['picking_type_id'])],
    'location_id':self.maps['stock.location'][rid(p['location_id'])],'location_dest_id':self.maps['stock.location'][rid(p['location_dest_id'])],
    'scheduled_date':p['scheduled_date'],'origin':p['origin'],'partner_id':self.maps['res.partner'].get(rid(p['partner_id']),False)}
  for batch in chunks(new,100):
   ids=self.mutate('stock.picking','create',[[pv(p) for p in batch]],{'context':{'tracking_disable':True,'mail_create_nolog':True}})
   pm.update({p['id']:t for p,t in zip(batch,ids)});self.persist()
  fields=['.id','picking_type_id/.id','location_id/.id','location_dest_id/.id','scheduled_date','origin','partner_id/.id']
  rows=[[pm[p['id']],v['picking_type_id'],v['location_id'],v['location_dest_id'],v['scheduled_date'],v['origin'],v['partner_id']] for p in picks if p['id'] in used for v in [pv(p)]]
  self.matrix('stock.picking',fields,rows)
  mm=self.maps.setdefault('stock.move',{});mm.update(reuse)
  newmoves=[self.sm[i] for i in sorted(mids) if i not in mm]
  for batch in chunks(newmoves,100):
   ids=self.mutate('stock.move','create',[[self.mv(m,picking=pm[rid(m['picking_id'])],state='cancel' if m['state']=='cancel' else 'confirmed') for m in batch]],{'context':{'tracking_disable':True}})
   require(len(ids)==len(batch),'Missing created moves');mm.update({m['id']:t for m,t in zip(batch,ids)});self.persist()
  update=[(self.sm[s],t) for s,t in reuse.items()]
  sample=self.mv(update[0][0],picking=pm[rid(update[0][0]['picking_id'])])
  ks=list(sample);relation={'company_id','product_id','product_uom','location_id','location_dest_id','rule_id','location_final_id','picking_id','sale_line_id','purchase_line_id'}
  fields=['.id']+[k+'/.id' if k in relation else k for k in ks]
  rows=[[t]+[self.mv(m,picking=pm[rid(m['picking_id'])],state='cancel' if m['state']=='cancel' else 'confirmed')[k] for k in ks] for m,t in update]
  self.matrix('stock.move',fields,rows)
  self.attach('stock.picking',list(pm.items()));self.attach('stock.move',[(s,t) for s,t in mm.items() if s in mids])
  self.j['phases']['transfers']=True;self.persist();print('transfers ready',len(pm),len(mids),flush=True)
 def prepare_mos(self,reference_mode):
  if self.j['phases'].get('mo'):return
  require(reference_mode in ['origin','field'],'Unknown reference mode')
  if reference_mode=='field':
   meta=self.b.call('mrp.production','fields_get',[['x_studio_reference_no']],{'attributes':['type','store']})
   require(meta.get('x_studio_reference_no',{}).get('type')=='char','Reference field missing')
  require(not self.j['phases'].get('mo_preparation_started') or self.j.pop('reviewed_mo_resume',False),'Interrupted MO preparation must be reviewed')
  self.j['phases']['mo_preparation_started']=True;self.j['reference_mode']=reference_mode;self.persist()
  mapping=self.maps.setdefault('mrp.production',{});mm=self.maps.setdefault('stock.move',{})
  source=[m for m in self.mos.values() if m['id'] not in self.p['blocked_mo']]
  def map_moves(batch,created):
   cm=self.b.read('stock.move',[i for m in created for k in ['move_raw_ids','move_finished_ids'] for i in m[k]],['product_id','product_uom','product_uom_qty','location_id','location_dest_id','state'])
   ci=index(cm)
   for s,t in zip(batch,created):
    require(t['company_id'][0]==1 and t['state']=='confirmed','Unexpected confirmed MO')
    for key in ['move_raw_ids','move_finished_ids']:
     expected=[self.mm[i] for i in s[key] if self.mm[i]['state']=='done'];actual=[ci[i] for i in t[key]]
     require(len(expected)==len(actual),'MO moves were merged/added');used=set()
     for m in expected:
      v=self.mv(m);identity=[x for x in actual if x['id'] not in used and all(rid(x[k])==v[k] for k in ['product_id','product_uom','location_id','location_dest_id'])]
      matches=[x for x in identity if abs(x['product_uom_qty']-v['product_uom_qty'])<1e-6]
      if not matches and len(identity)==1 and abs(identity[0]['product_uom_qty']-v['product_uom_qty'])<=0.00501:
       matches=identity;self.j.setdefault('precision_differences',{})[str(m['id'])]={'source_mo':s['id'],'source_move':m['id'],'target_move':identity[0]['id'],'source_qty':v['product_uom_qty'],'target_qty':identity[0]['product_uom_qty']}
      require(len(matches)==1,'Ambiguous MO move mapping');mm[m['id']]=matches[0]['id'];used.add(matches[0]['id'])
   self.persist()
  existing=[s for s in source if s['id'] in mapping]
  if existing:
   created=self.b.read('mrp.production',[mapping[s['id']] for s in existing],['move_raw_ids','move_finished_ids','company_id','state','origin'])
   map_moves(existing,created)
  for batch in chunks([s for s in source if s['id'] not in mapping],25):
   values=[]
   for s in batch:
    v={'name':s['name'],'company_id':1,'product_id':self.maps['product.product'][rid(s['product_id'])],'product_qty':s['product_qty'],
       'product_uom_id':self.maps['uom.uom'][rid(s['product_uom_id'])],'bom_id':False,
       'picking_type_id':self.maps['stock.picking.type'][rid(s['picking_type_id'])],
       'location_src_id':self.maps['stock.location'][rid(s['location_src_id'])],'location_dest_id':self.maps['stock.location'][rid(s['location_dest_id'])],
       'origin':(s.get('x_studio_reference_no') or s['origin'] or False) if reference_mode=='origin' else s['origin'],
       'date_start':s['date_start'] or s['date_planned_start'],'date_finished':s['date_finished']}
    if reference_mode=='field':v['x_studio_reference_no']=s.get('x_studio_reference_no') or False
    for k,kind in [('move_raw_ids','raw'),('move_finished_ids','finished')]:
     v[k]=[(0,0,self.mv(self.mm[i],kind=kind,state='draft')) for i in s[k] if self.mm[i]['state']=='done']
    producing_lots={self.maps['stock.lot'][rid(x['lot_id'])] for x in self.ml.values() if rid(x['move_id']) in s['move_finished_ids'] and rid(x['product_id'])==rid(s['product_id']) and x['lot_id']}
    if producing_lots:v['lot_producing_ids']=[(6,0,sorted(producing_lots))]
    values.append(v)
   ids=self.mutate('mrp.production','create',[values],{'context':{'tracking_disable':True,'mail_create_nolog':True}})
   require(len(ids)==len(batch),'Missing created MO');mapping.update({s['id']:t for s,t in zip(batch,ids)});self.persist()
   self.mutate('mrp.production','action_confirm',[ids],{'context':{'tracking_disable':True}})
   created=self.b.read('mrp.production',ids,['move_raw_ids','move_finished_ids','company_id','state','origin'])
   map_moves(batch,created)
   self.persist();print('MO prepared',len(mapping),flush=True)
  self.matrix('mrp.production',['.id','qty_producing'],[[mapping[s['id']],s['product_qty']] for s in source])
  self.attach('mrp.production',list(mapping.items()));self.attach('stock.move',[(s,t) for s,t in mm.items() if s in self.mm])
  self.j['phases']['mo']=True;self.persist()
 def prepare_links_and_lines(self):
  if self.j['phases'].get('details'):return
  require(not self.j['phases'].get('details_started'),'Interrupted details preparation must be reviewed')
  self.j['phases']['details_started']=True;self.persist();mm=self.maps['stock.move'];pm=self.maps['stock.picking']
  rows=[]
  for s,t in mm.items():
   m=self.sm.get(s) or self.mm[s]
   rows.append([t,','.join(str(mm[i]) for i in m['move_orig_ids'] if i in mm),','.join(str(mm[i]) for i in m['move_dest_ids'] if i in mm),mm.get(rid(m['origin_returned_move_id']),False)])
  self.matrix('stock.move',['.id','move_orig_ids/.id','move_dest_ids/.id','origin_returned_move_id/.id'],rows)
  self.matrix('stock.picking',['.id','backorder_id/.id'],[[t,pm.get(rid(self.sp[s]['backorder_id']),False)] for s,t in pm.items()])
  moids=list(self.maps.get('mrp.production',{}).values())
  if moids:
   existing=self.b.search_read('stock.move.line',[['move_id','in',[t for s,t in mm.items() if s in self.mm]],['company_id','=',1]],['state'])
   require(all(x['state']!='done' for x in existing),'MO already completed')
   for batch in chunks([x['id'] for x in existing],500):self.mutate('stock.move.line','unlink',[batch])
  source=[x for x in list(self.sl.values())+list(self.ml.values()) if rid(x['move_id']) in mm and x['qty_done']>0]
  mapping=self.maps.setdefault('stock.move.line',{})
  for batch in chunks(source,100):
   values=[]
   for x in batch:
    tid=self.maps['product.product'][rid(x['product_id'])];product=self.product[tid]
    require(product['tracking']=='none' or x['lot_id'],'Source missing lot for target tracked product '+str(x['id']))
    require(not x['owner_id'],'Owner mapping needs separate review')
    values.append({'company_id':1,'move_id':mm[rid(x['move_id'])],'product_id':tid,'product_uom_id':self.maps['uom.uom'][rid(x['product_uom_id'])],
     'location_id':self.maps['stock.location'][rid(x['location_id'])],'location_dest_id':self.maps['stock.location'][rid(x['location_dest_id'])],
     'lot_id':self.maps['stock.lot'].get(rid(x['lot_id']),False),'quantity':x['qty_done'],'picked':True,'date':x['date'],
     'package_id':self.maps['stock.package'].get(rid(x['package_id']),False),'result_package_id':self.maps['stock.package'].get(rid(x['result_package_id']),False)})
   ids=self.mutate('stock.move.line','create',[values],{'context':{'tracking_disable':True}})
   require(len(ids)==len(batch),'Missing stock detail rows');mapping.update({x['id']:t for x,t in zip(batch,ids)});self.persist()
   print('details prepared',len(mapping),'/',len(source),flush=True)
  self.attach('stock.move.line',list(mapping.items()));self.j['phases']['details']=True;self.persist()
 def prepare(self,reference_mode):
  self.preflight();self.prepare_lots();self.prepare_packages();self.prepare_transfers()
  if reference_mode:self.prepare_mos(reference_mode)
  else:return
  self.prepare_links_and_lines()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--reference-mode',choices=['origin','field']);args=parser.parse_args()
 migration=Migration()
 try:
  if args.prepare:migration.prepare(args.reference_mode)
  print(json.dumps({'phases':migration.j['phases'],'blocked_pickings':len(migration.blocked_source),'blocked_MO':len(migration.p['blocked_mo'])}),flush=True)
 except Exception:
  migration.j['last_error']=traceback.format_exc();migration.persist();raise
if __name__=='__main__':main()
