"""Scoped Sue stock correction; preflight is read-only, --apply requires operator authorization."""
import argparse, json, runpy, socket
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[6]
OUT=ROOT/'outputs/pysb-sue-stock-review-20261020'
OLD=ROOT/'outputs/pysb-stock-migration-20261012'
def load(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,v):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(p)
def rid(v):return v[0] if isinstance(v,list) and v else False
def require(v,msg):
 if not v:raise RuntimeError(msg)

class Repair:
 def __init__(self):
  socket.setdefaulttimeout(60)
  Reader=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']
  self.a=Reader(ROOT/'mcp-server-odoo/envs/v14-prod/.env');self.b=Reader(ROOT/'mcp-server-odoo/envs/v19-staging/.env')
  require((self.b.url,self.b.db)==('https://py-staging.odoo.com','py19-staging-39654560'),'Wrong target')
  require(self.b.read('res.company',[1],['name'])[0]['name']=='PAO YEANG SDN BHD','Wrong company')
  self.plan=load(OUT/'approval-change-set.json');self.old=load(OLD/'execution-journal.json');self.man=load(OLD/'execution-manifest.json')
  self.maps={model:{int(s):t for s,t in mp.items()} for model,mp in self.man['maps'].items()}
  for model,mp in self.old['maps'].items():self.maps.setdefault(model,{}).update({int(s):t for s,t in mp.items()})
  self.path=OUT/'stock-repair-journal.json'
  self.j=load(self.path) if self.path.exists() else {'database':self.b.db,'company_id':1,'operator_authorization':'Bruce: hãy sửa trên v19 staging; 17 verified scraps and missing PTC delivery chain only','started_utc':datetime.now(timezone.utc).isoformat(),'operations':[],'scraps':{},'pickings':{},'maps':{}}
 def mutate(self,model,method,args,kwargs=None):
  kwargs=kwargs or {};kwargs['context']={'tracking_disable':True,'mail_notrack':True,'mail_create_nolog':True,'mail_create_nosubscribe':True,**kwargs.get('context',{})}
  op={'model':model,'method':method,'args':args,'kwargs':kwargs,'status':'intent','utc':datetime.now(timezone.utc).isoformat()};self.j['operations'].append(op);save(self.path,self.j)
  try:
   result=self.b.call(model,method,args,kwargs);op.update(status='returned',result=result);save(self.path,self.j);return result
  except Exception as ex:
   op.update(status='uncertain_or_failed',error=str(ex));save(self.path,self.j);raise
 def preflight(self):
  mids=[x['source_move_id'] for x in self.plan['change_set_A']['scraps']]+[500291,500292,500293]
  fs=['name','date','create_date','write_date','state','company_id','product_id','product_uom','quantity_done','location_id','location_dest_id','picking_id','move_line_ids','sale_line_id','move_orig_ids','move_dest_ids']
  sm=self.a.read('stock.move',mids,fs);require(len(sm)==20 and all(x['state']=='done' and rid(x['company_id'])==1 for x in sm),'Source set changed')
  sl=self.a.read('stock.move.line',[i for x in sm for i in x['move_line_ids']],['move_id','product_id','product_uom_id','qty_done','lot_id','package_id','result_package_id','owner_id','location_id','location_dest_id','date'])
  require(len(sl)==20 and all(not x['package_id'] and not x['result_package_id'] and not x['owner_id'] for x in sl),'Unexpected source dimensions')
  picks=self.a.read('stock.picking',[183094,183095,183096],['name','state','company_id','date_done','scheduled_date','origin','partner_id','picking_type_id','location_id','location_dest_id','move_lines'])
  pids=[x['target_product_id'] for x in self.plan['change_set_A']['scraps']]+[116242]
  products=self.b.read('product.product',pids,['name','display_name','tracking','uom_id','company_id','standard_price','is_storable','default_code','barcode'])
  quants=self.b.search_read('stock.quant',[['company_id','=',1],['product_id','in',pids]],['product_id','quantity','reserved_quantity','location_id','lot_id','package_id','owner_id'])
  lots=self.b.search_read('stock.lot',[['product_id','=',116242]],['name','product_id','company_id'])
  partner_id=self.maps.get('res.partner',{}).get(33087)
  partner_candidates=self.b.search_read('res.partner',[['name','ilike','EASTOOL']],['name','company_id','active','parent_id','commercial_partner_id'])
  ext=self.b.search_read('ir.model.data',[['module','=','pysb_v14'],['model','in',['stock.move','stock.picking']],['name','in',['stock_move_'+str(i) for i in mids]+['stock_picking_'+str(i) for i in [183094,183095,183096]]]],['model','name','res_id'])
  result={'database':self.b.db,'source_moves':sm,'source_lines':sl,'source_pickings':picks,'products':products,'target_quants':quants,'ptc_target_lots':lots,'mapped_partner_id':partner_id,'partner_candidates':partner_candidates,'existing_external_ids':ext,'target_locations':self.b.read('stock.location',sorted({self.maps['stock.location'][rid(x[f])] for x in sl for f in ['location_id','location_dest_id']}),['usage','complete_name','company_id']),'picking_types':self.b.read('stock.picking.type',sorted({self.maps['stock.picking.type'][rid(x['picking_type_id'])] for x in picks}),['name','code','warehouse_id']),'source_product_ptc':self.a.read('product.product',[51370],['name','barcode','default_code','uom_id','tracking']),'scrap_schema':self.b.call('stock.scrap','fields_get',[],{'attributes':['type']}),'move_schema':self.b.call('stock.move','fields_get',[],{'attributes':['type']})}
  save(OUT/'repair-preflight.json',result)
  print(json.dumps({'phase':'preflight','products':len(products),'source_lines':len(sl),'ptc_lots':lots,'partner':partner_id,'partner_candidates':partner_candidates,'external_ids':ext,'locations':result['target_locations'],'picking_types':result['picking_types']},ensure_ascii=True),flush=True)
  return result
 def quants(self):
  return self.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','package_id','owner_id','quantity','reserved_quantity'])
 def ledger(self,rows):
  values=defaultdict(float)
  for q in rows:values[tuple(rid(q[k]) for k in ['product_id','location_id','lot_id','package_id','owner_id'])]+=q['quantity']
  return values
 def attach(self,model,sid,tid):
  name=model.replace('.','_')+'_'+str(sid)
  hits=self.b.search_read('ir.model.data',[['module','=','pysb_v14'],['name','=',name]],['model','res_id'])
  require(not hits or (len(hits)==1 and hits[0]['model']==model and hits[0]['res_id']==tid),'External ID conflict')
  if not hits:self.mutate('ir.model.data','create',[{'module':'pysb_v14','name':name,'model':model,'res_id':tid,'noupdate':True}])
  self.j['maps'].setdefault(model,{})[str(sid)]=tid;save(self.path,self.j)
 def date_and_check(self,mid,source,line,tid,lotid):
  move=self.b.read('stock.move',[mid],['state','move_line_ids','quantity','product_id','location_id','location_dest_id'])[0]
  require(move['state']=='done' and len(move['move_line_ids'])==1,'Unexpected completed move')
  lid=move['move_line_ids'][0]
  self.mutate('stock.move','write',[[mid],{'date':source['date']}])
  self.mutate('stock.move.line','write',[[lid],{'date':source['date']}])
  actual=self.b.read('stock.move.line',[lid],['product_id','product_uom_id','quantity','lot_id','location_id','location_dest_id','date','state'])[0]
  require(actual['state']=='done' and rid(actual['product_id'])==tid and rid(actual['lot_id'])==lotid and abs(actual['quantity']-line['qty_done'])<1e-6 and actual['date']==source['date'],'Source/target completed detail differs')
  require(rid(actual['location_id'])==self.maps['stock.location'][rid(line['location_id'])] and rid(actual['location_dest_id'])==self.maps['stock.location'][rid(line['location_dest_id'])],'Locations differ')
  self.attach('stock.move',source['id'],mid);self.attach('stock.move.line',line['id'],lid)
  return lid
 def apply(self,data):
  require(not any(op['status'] in ['intent','uncertain_or_failed'] for op in self.j['operations']),'Interrupted/failed mutation requires read-back review before resuming')
  if not self.j.get('baseline'):
   require(not data['existing_external_ids'],'Source already mapped outside repair journal')
   self.j['baseline']={'quants':self.quants(),'masters':data['products'],'account_move_max':self.b.call('account.move','search',[[['company_id','=',1]]],{'limit':1,'order':'id desc'})}
   self.j['scope']={'scraps':[x['source_move_id'] for x in self.plan['change_set_A']['scraps']],'delivery_moves':[500293,500292,500291],'no_master_changes':True,'no_temporary_supply_changes':True}
   save(self.path,self.j)
  sm={x['id']:x for x in data['source_moves']};sl={rid(x['move_id']):x for x in data['source_lines']}
  # All target lots and quantities were proven before the first write. Run one scrap and verify before the rest.
  for row in self.plan['change_set_A']['scraps']:
   sid=row['source_move_id'];key=str(sid)
   if self.j['scraps'].get(key,{}).get('status')=='verified':continue
   require(key not in self.j['scraps'],'Interrupted scrap requires review')
   src=sm[sid];line=sl[sid];qty=row['quantity'];pid=row['target_product_id'];lotid=row['target_lot_id']
   require(abs(line['qty_done']-qty)<1e-6 and src['date']==row['date_utc'],'Source changed from approved scrap')
   before=self.ledger(self.quants());qkey=(pid,5,lotid,False,False);destkey=(pid,11,lotid,False,False)
   require(before[qkey]+1e-6>=qty,'Insufficient exact-lot stock')
   require(not self.b.search_read('stock.scrap',[['origin','=',f"PYSB-SUE-20261020 | v14 {row['source_reference']}"]],['id']),'Existing scrap without journal')
   rec={'status':'intent','source_move':sid,'reference':row['source_reference'],'before':[[list(qkey),before[qkey]],[list(destkey),before[destkey]]],'expected_quantity':qty};self.j['scraps'][key]=rec;save(self.path,self.j)
   sid19=self.mutate('stock.scrap','create',[{'company_id':1,'product_id':pid,'product_uom_id':row['target_uom_id'],'scrap_qty':qty,'lot_id':lotid,'location_id':5,'scrap_location_id':11,'origin':f"PYSB-SUE-20261020 | v14 {row['source_reference']}"}]);rec['target_scrap']=sid19;save(self.path,self.j)
   action=self.mutate('stock.scrap','action_validate',[[sid19]])
   require(not isinstance(action,dict) or not action.get('res_model'),'Unexpected scrap wizard; read-back required')
   done=self.b.read('stock.scrap',[sid19],['state','move_ids'])[0];require(done['state']=='done' and len(done['move_ids'])==1,'Scrap not completed')
   mid=done['move_ids'][0];rec['target_move']=mid;save(self.path,self.j)
   lid=self.date_and_check(mid,src,line,pid,lotid)
   self.mutate('stock.scrap','write',[[sid19],{'date_done':src['date']}])
   after=self.ledger(self.quants());require(abs(after[qkey]-before[qkey]+qty)<1e-6 and abs(after[destkey]-before[destkey]-qty)<1e-6,'Scrap quant delta mismatch')
   rec.update(status='verified',target_line=lid,after=[[list(qkey),after[qkey]],[list(destkey),after[destkey]]]);save(self.path,self.j)
   print(json.dumps({'phase':'scrap_verified','source':row['source_reference'],'target_scrap':sid19,'target_move':mid}),flush=True)
  # Create exactly the three source delivery steps. No SO/PO import or master changes.
  sources=sorted(data['source_pickings'],key=lambda x:x['date_done']);pid=116242;lotid=24778;partner=81323
  require(len(data['partner_candidates'])==1 and data['partner_candidates'][0]['id']==partner,'Customer mapping needs review')
  require(any(x['id']==lotid and x['name']=='27082025' for x in data['ptc_target_lots']),'PTC lot changed')
  product=next(x for x in data['products'] if x['id']==pid)
  require(data['source_product_ptc'][0]['barcode']==product['barcode'] and data['source_product_ptc'][0]['name']==product['name'],'PTC identity differs')
  for srcpick in sources:
   key=str(srcpick['id'])
   if key in self.j['pickings']:continue
   source_mid=srcpick['move_lines'][0];src=sm[source_mid];line=sl[source_mid]
   require(len(srcpick['move_lines'])==1 and abs(line['qty_done']-1)<1e-6,'PTC source scope differs')
   rec={'status':'intent','source_picking':srcpick['id'],'source_move':source_mid,'reference':srcpick['name']};self.j['pickings'][key]=rec;save(self.path,self.j)
   vals={'company_id':1,'picking_type_id':self.maps['stock.picking.type'][rid(srcpick['picking_type_id'])],'location_id':self.maps['stock.location'][rid(srcpick['location_id'])],'location_dest_id':self.maps['stock.location'][rid(srcpick['location_dest_id'])],'scheduled_date':srcpick['scheduled_date'],'partner_id':partner,'origin':f"PYSB-SUE-20261020 | v14 {srcpick['name']} | SO-52864",'move_type':'direct','note':json.dumps({'source_database':self.a.db,'source_picking':srcpick,'source_move':src,'purpose':'Missing July delivery from pre-July SO; standalone, no order import'},ensure_ascii=False)}
   pick=self.mutate('stock.picking','create',[vals]);rec['target_picking']=pick;save(self.path,self.j)
   mv={'company_id':1,'product_id':pid,'product_uom':rid(product['uom_id']),'product_uom_qty':1.0,'location_id':vals['location_id'],'location_dest_id':vals['location_dest_id'],'location_final_id':vals['location_dest_id'],'date':src['date'],'state':'confirmed','procure_method':'make_to_stock','propagate_cancel':False,'rule_id':False,'sale_line_id':False,'purchase_line_id':False,'partner_id':partner,'picking_id':pick,'origin':vals['origin'],'description_picking_manual':json.dumps({'source_move':src,'source_line':line},ensure_ascii=False)}
   mid=self.mutate('stock.move','create',[mv]);rec['target_move']=mid;save(self.path,self.j)
   lid=self.mutate('stock.move.line','create',[{'company_id':1,'picking_id':pick,'move_id':mid,'product_id':pid,'product_uom_id':rid(product['uom_id']),'quantity':1.0,'picked':True,'location_id':vals['location_id'],'location_dest_id':vals['location_dest_id'],'lot_id':lotid,'date':src['date']}]);rec.update(target_line=lid,status='prepared');save(self.path,self.j)
  bysrc={r['source_move']:r['target_move'] for r in self.j['pickings'].values()}
  if not self.j.get('delivery_links_prepared'):
   for s,t in bysrc.items():
    dest=[bysrc[i] for i in sm[s]['move_dest_ids'] if i in bysrc]
    if dest:self.mutate('stock.move','write',[[t],{'move_dest_ids':[(6,0,dest)]}])
   self.j['delivery_links_prepared']=True;save(self.path,self.j)
  for srcpick in sources:
   rec=self.j['pickings'][str(srcpick['id'])]
   if rec['status']=='verified':continue
   require(rec['status']=='prepared','Interrupted delivery preparation requires review')
   pick=rec['target_picking'];mid=rec['target_move'];src=sm[rec['source_move']];line=sl[src['id']]
   stock=self.ledger(self.quants());loc=self.maps['stock.location'][rid(line['location_id'])];require(stock[(pid,loc,lotid,False,False)]+1e-6>=1,'Insufficient PTC lot for next source step')
   require(self.b.read('stock.picking',[pick],['state'])[0]['state']!='done','Done picking without verified journal; review required')
   action=self.mutate('stock.picking','button_validate',[[pick]],{'context':{'skip_backorder':True,'skip_redirection':True,'picking_ids_not_to_backorder':[pick]}})
   if isinstance(action,dict) and action.get('res_model')=='expiry.picking.confirmation':
    ctx=action.get('context',{});wizard=self.mutate('expiry.picking.confirmation','create',[{'lot_ids':ctx.get('default_lot_ids',[]),'picking_ids':[(6,0,[pick])]}],{'context':ctx});self.mutate('expiry.picking.confirmation','process',[[wizard]],{'context':ctx})
   else:require(not isinstance(action,dict) or not action.get('res_model'),'Unexpected delivery wizard; read-back required')
   actual=self.b.read('stock.picking',[pick],['state','move_ids'])[0];require(actual['state']=='done' and actual['move_ids']==[mid],'Unexpected delivery completion')
   self.date_and_check(mid,src,line,pid,lotid);self.mutate('stock.picking','write',[[pick],{'date_done':srcpick['date_done'],'scheduled_date':srcpick['scheduled_date']}]);self.attach('stock.picking',srcpick['id'],pick)
   rec['status']='verified';save(self.path,self.j);print(json.dumps({'phase':'delivery_verified','source':srcpick['name'],'target_picking':pick,'target_move':mid}),flush=True)
  self.verify()
 def verify(self):
  require(len(self.j['scraps'])==17 and all(r['status']=='verified' for r in self.j['scraps'].values()),'Incomplete scraps')
  require(len(self.j['pickings'])==3 and all(r['status']=='verified' for r in self.j['pickings'].values()),'Incomplete delivery')
  before=self.ledger(self.j['baseline']['quants']);afterrows=self.quants();after=self.ledger(afterrows);expected=defaultdict(float)
  for x in self.plan['change_set_A']['scraps']:
   key=(x['target_product_id'],5,x['target_lot_id'],False,False);dest=(x['target_product_id'],11,x['target_lot_id'],False,False);expected[key]-=x['quantity'];expected[dest]+=x['quantity']
  # Customers (location 2) has no company_id, so its quants are outside this
  # company-1 ledger. The completed delivery line verifies the external leg.
  expected[(116242,5,24778,False,False)]-=1
  differences=[{'key':list(k),'before':before[k],'after':after[k],'expected_delta':expected[k],'actual_delta':after[k]-before[k]} for k in set(before)|set(after)|set(expected) if abs(after[k]-before[k]-expected[k])>1e-6]
  require(not differences,'Unexpected changes in company quant ledger: '+str(differences[:5]))
  masters=self.b.read('product.product',[x['id'] for x in self.j['baseline']['masters']],['name','default_code','barcode','tracking','uom_id'])
  old={x['id']:x for x in self.j['baseline']['masters']};require(all(all(x[f]==old[x['id']][f] for f in ['name','default_code','barcode','tracking','uom_id']) for x in masters),'Master changed')
  ids=[r['target_move'] for r in self.j['scraps'].values()]+[r['target_move'] for r in self.j['pickings'].values()]
  moves=self.b.read('stock.move',ids,['state','date','product_id','quantity','move_line_ids','value','account_move_id','location_id','location_dest_id'])
  require(len(moves)==20 and all(x['state']=='done' for x in moves),'Final moves are not all done')
  flow=self.b.search_read('stock.picking',[['company_id','=',1],['origin','=like','PYSB-SUE-20261020%']],['name','state','move_ids','date_done','origin'])
  require({x['id'] for x in flow}=={r['target_picking'] for r in self.j['pickings'].values()} and all(x['state']=='done' for x in flow),'Unexpected push-route pickings')
  base=self.j['baseline']['account_move_max'];newaccount=self.b.search_read('account.move',[['company_id','=',1],['id','>',base[0] if base else 0]],['name','move_type','state','date'])
  require(not any(x['move_type']!='entry' for x in newaccount),'Unexpected new invoice/bill; review required')
  product_ids=sorted({x['target_product_id'] for x in self.plan['change_set_A']['scraps']}|{116242})
  locs=self.b.search_read('stock.location',[['usage','in',['internal','transit']],'|',['company_id','=',1],['company_id','=',False]],['id'])
  quantities=self.b.call('product.product','read',[product_ids],{'fields':['name','qty_available'],'context':{'to_date':'2026-07-31 15:00:00','location':[x['id'] for x in locs],'compute_child':False,'force_company':1}})
  oldsource=load(OUT/'all-internal-quantities.json')['source']['products'];sourcebyid={x['id']:x for x in oldsource};pm={int(k):v for k,v in load(OUT/'change-evidence.json')['product_mapping'].items()};pm[51370]=116242;reverse={v:k for k,v in pm.items()}
  comparison=[{'target_product':x['id'],'source_product':reverse[x['id']],'name':x['name'],'source_quantity':sourcebyid[reverse[x['id']]]['qty_available'],'target_quantity':x['qty_available'],'delta':x['qty_available']-sourcebyid[reverse[x['id']]]['qty_available']} for x in quantities]
  require(all(abs(x['delta'])<=0.00501 for x in comparison),'Corrected products do not match source as of cutoff')
  result={'database':self.b.db,'company_id':1,'verified_utc':datetime.now(timezone.utc).isoformat(),'scraps_done':17,'delivery_pickings_done':3,'done_stock_moves':len(moves),'unexpected_quant_differences':differences,'master_fields_preserved':True,'temporary_supply_preserved':True,'new_account_moves':newaccount,'stock_moves':moves,'delivery_records':flow,'quantity_comparison':comparison,'scraps':self.j['scraps'],'pickings':self.j['pickings']}
  save(OUT/'stock-repair-result.json',result);self.j['status']='verified';save(self.path,self.j);print(json.dumps({'phase':'final_verified','scraps':17,'pickings':3,'moves':len(moves),'products_match':len(comparison),'unexpected_quant_changes':len(differences)}),flush=True)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--verify',action='store_true');args=parser.parse_args();r=Repair()
 if args.verify:r.verify();return
 r.preflight()
 if args.apply:r.apply(load(OUT/'repair-preflight.json'))
if __name__=='__main__':main()
