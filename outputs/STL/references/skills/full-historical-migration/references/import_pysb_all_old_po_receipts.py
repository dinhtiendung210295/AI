"""Standalone replay of approved old-PO late receipts; existing masters only."""
import json,runpy
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/complete_pysb_stock_migration.py'))
def main():
 m=H['Completion']();rid=H['rid'];req=H['require'];save=H['H']['save'];d=H['load']('old-po-late-receipts-discovery.json');mapperh=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))
 records=m.j.setdefault('standalone_source_receipts',[]);known={x['source_move']:x['target_move'] for x in records};known.update(m.maps['stock.move'])
 moves={x['id']:x for x in d['moves']};picks={x['id']:x for x in d['pickings']};lines=defaultdict(list)
 for x in d['lines']:
  if x['qty_done']>0:lines[rid(x['move_id'])].append(x)
 needed={rid(x['product_id']) for x in d['lines'] if x['qty_done']>0};extra=needed-set(m.maps['product.product'])
 source=m.a.read('product.product',sorted(extra),['name','display_name','default_code','barcode','company_id','active'])
 mapper=mapperh['TargetMapper'](m.b);pm=mapper.products(source);m.maps['product.product'].update(pm)
 targetproducts=m.b.read('product.product',sorted(set(m.maps['product.product'].values())),['name','default_code','barcode','tracking','uom_id','packing_ratio','active','is_storable'])
 m.product={x['id']:x for x in targetproducts};m.uoms=H['index'](m.b.search_read('uom.uom',[],['name','factor','rounding']))
 issues=list(mapper.exceptions);by_pick=defaultdict(list)
 for sid,s in moves.items():
  if sid in known:continue
  if not lines[sid]:continue
  bad=[]
  for x in lines[sid]:
   pid=m.maps['product.product'].get(rid(x['product_id']))
   if not pid:bad.append('missing product mapping');continue
   if x['owner_id'] or x['package_id'] or x['result_package_id']:bad.append('owner/package mapping required')
   if m.product[pid]['tracking']!='none' and not x['lot_id']:bad.append('missing required lot')
   if m.product[pid]['tracking']=='serial' and x['qty_done']!=1:bad.append('serial quantity is not one')
  if bad:issues.append({'source_move':sid,'source_picking':rid(s['picking_id']),'reason':bad});continue
  by_pick[rid(s['picking_id'])].append(sid)
 # A source picking with an unresolved line remains entirely out of this run.
 blocked={x['source_picking'] for x in issues if x.get('source_picking')}
 by_pick={p:ids for p,ids in by_pick.items() if p not in blocked}
 types=m.b.search_read('stock.picking.type',[['company_id','=',1]],['code','default_location_src_id','default_location_dest_id'])
 for p,ids in list(by_pick.items()):
  s=moves[ids[0]];src=m.maps['stock.location'][rid(s['location_id'])];dst=m.maps['stock.location'][rid(s['location_dest_id'])];code='incoming' if m.locations[src]['usage']=='supplier' else 'internal'
  hits=[t for t in types if t['code']==code and rid(t['default_location_src_id'])==src and rid(t['default_location_dest_id'])==dst]
  if not hits:hits=[t for t in types if t['code']==code and rid(t['default_location_dest_id'])==dst]
  if len(hits)!=1 and rid(picks[p]['picking_type_id']) in m.maps['stock.picking.type']:
   mapped_type=m.maps['stock.picking.type'][rid(picks[p]['picking_type_id'])]
   hits=[t for t in types if t['id']==mapped_type]
  if len(hits)!=1:issues.append({'source_picking':p,'reason':'ambiguous picking type'});del by_pick[p]
  else:picks[p]['target_type']=hits[0]['id']
 save(m.path.parent/'all-old-po-receipts-preflight.json',{'selected_pickings':by_pick,'exceptions':issues,'extra_product_mapping':pm})
 # Retain baseline evidence for newly included, existing products. Do not edit masters.
 baseids={x['id'] for x in m.j['baseline_products']}
 for x in targetproducts:
  if x['id'] not in baseids:m.j['baseline_products'].append({k:v for k,v in x.items() if k!='is_storable'})
 m.p['maps']['product.product']=m.maps['product.product'];m.p['target_products']=targetproducts
 if not (m.path.parent/'execution-manifest-before-old-po.json').exists():save(m.path.parent/'execution-manifest-before-old-po.json',H['load']('execution-manifest.json'))
 save(m.path.parent/'execution-manifest.json',m.p);m.persist()
 lotids={rid(x['lot_id']) for p,ids in by_pick.items() for i in ids for x in lines[i] if x['lot_id']}
 source_lots=m.a.read('stock.production.lot',sorted(lotids),['name','product_id','company_id'])
 target_lots=m.b.search_read('stock.lot',[['company_id','=',1]],['name','product_id']);lookup=defaultdict(list)
 for x in target_lots:lookup[(rid(x['product_id']),x['name'])].append(x['id'])
 for s in source_lots:
  pid=m.maps['product.product'][rid(s['product_id'])];hits=lookup[(pid,s['name'])];req(len(hits)<=1,'Ambiguous target lot')
  if s['id'] in m.maps['stock.lot']:req(not hits or m.maps['stock.lot'][s['id']]==hits[0],'Lot map conflict');continue
  target=hits[0] if hits else m.mutate('stock.lot','create',[{'name':s['name'],'product_id':pid,'company_id':1}])
  lookup[(pid,s['name'])]=[target];m.maps['stock.lot'][s['id']]=target;m.persist()
 m.attach('stock.lot',[(s['id'],m.maps['stock.lot'][s['id']]) for s in source_lots])
 # Prepare complete chains before native validation so Odoo can follow links
 # and does not push duplicate Input→Stock moves.
 for p,ids in sorted(by_pick.items(),key=lambda item:(picks[item[0]]['date_done'],item[0])):
  if all(i in known for i in ids):continue
  req(not any(i in known for i in ids),'Partially prepared picking requires recovery review')
  sp=picks[p];s=moves[ids[0]];ref=f"PYSB-OLD-PO-SUPPLY | v14 {sp['name']} | {sp['origin']}"
  note={'purpose':'REAL V14 LATE RECEIPT FROM PRE-JULY PO; STANDALONE WITHOUT PO IMPORT','source_database':m.a.db,'company_id':1,'source_picking':sp,'source_moves':ids}
  target=m.mutate('stock.picking','create',[{'company_id':1,'picking_type_id':sp['target_type'],'location_id':m.maps['stock.location'][rid(s['location_id'])],'location_dest_id':m.maps['stock.location'][rid(s['location_dest_id'])],'scheduled_date':sp['date_done'],'origin':ref,'note':json.dumps(note,ensure_ascii=False),'move_type':'direct'}])
  m.mutate('ir.model.data','create',[{'module':'pysb_standalone_supply','name':'source_picking_'+str(p),'model':'stock.picking','res_id':target,'noupdate':True}])
  for sid in ids:
   s=moves[sid];rec={'source_move':sid,'source_picking':p,'reference':ref,'status':'preparing','date':s['date'],'source_qty':sum(x['qty_done'] for x in lines[sid]),'target_picking':target,'note':note};records.append(rec);m.persist()
   vals=m.mv(s,picking=target);vals.update(purchase_line_id=False,sale_line_id=False,origin=ref,description_picking_manual=json.dumps({'source_move':s,'source_lines':lines[sid],'purpose':note['purpose']},ensure_ascii=False))
   mid=m.mutate('stock.move','create',[vals]);rec['target_move']=mid;known[sid]=mid;m.persist()
   deltas=defaultdict(float);lids=[]
   for x in lines[sid]:
    values={'company_id':1,'picking_id':target,'move_id':mid,'product_id':m.maps['product.product'][rid(x['product_id'])],'product_uom_id':m.maps['uom.uom'][rid(x['product_uom_id'])],'quantity':m.effective_qty(x),'picked':True,'location_id':m.maps['stock.location'][rid(x['location_id'])],'location_dest_id':m.maps['stock.location'][rid(x['location_dest_id'])],'lot_id':m.maps['stock.lot'].get(rid(x['lot_id']),False),'date':s['date']}
    lids.append(m.mutate('stock.move.line','create',[values]));q=m.qty(x);deltas[m.quantkey(x)]-=q;deltas[m.quantkey(x,True)]+=q
   rec.update(status='prepared',target_lines=lids,deltas=[[list(k),v] for k,v in deltas.items()]);m.persist()
   m.mutate('ir.model.data','create',[{'module':'pysb_standalone_supply','name':'move_'+str(sid),'model':'stock.move','res_id':mid,'noupdate':True}])
 for rec in records:
  sid=rec['source_move']
  if rec['status']!='prepared' or sid not in moves:continue
  dest=[known[i] for i in moves[sid]['move_dest_ids'] if i in known]
  # Add storage link for v14 chains with incomplete linkage, same PO/product.
  if not dest and m.locations[m.maps['stock.location'][rid(moves[sid]['location_id'])]]['usage']=='supplier':
   s=moves[sid];origin=picks[rid(s['picking_id'])]['origin']
   dest=[known[i] for i,t in moves.items() if i in known and rid(t['product_id'])==rid(s['product_id']) and rid(t['location_id'])==rid(s['location_dest_id']) and picks[rid(t['picking_id'])]['origin']==origin]
  if dest:m.mutate('stock.move','write',[[rec['target_move']],{'move_dest_ids':[(6,0,dest)]}])
 pending=[(p,ids) for p,ids in by_pick.items() if any(r['source_move'] in ids and r['status']=='prepared' for r in records)]
 for p,ids in sorted(pending,key=lambda item:(picks[item[0]]['date_done'],item[0])):
  group=[r for r in records if r['source_move'] in ids];target=group[0]['target_picking'];balance=m.ledger(m.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','package_id','owner_id','quantity']));need=defaultdict(float)
  for sid in ids:
   for x in lines[sid]:
    key=m.quantkey(x)
    if m.product[key[0]]['is_storable'] and m.locations[key[1]]['usage'] in ['internal','transit']:need[key]+=m.qty(x)
  shortage=[{'key':k,'available':balance[k],'required':q} for k,q in need.items() if balance[k]+1e-6<q]
  if shortage:
   for r in group:r['status']='blocked_stock';r['shortage']=shortage
   m.persist();continue
  result=m.mutate('stock.picking','button_validate',[[target]],{'context':{'skip_backorder':True,'skip_redirection':True,'picking_ids_not_to_backorder':[target]}})
  req(not isinstance(result,dict) or not result.get('res_model'),'Unexpected native wizard; inspect state before retry')
  actual=m.b.read('stock.picking',[target],['state','move_ids'])[0];req(actual['state']=='done' and set(actual['move_ids'])=={r['target_move'] for r in group},'Unexpected picking result')
  m.mutate('stock.picking','write',[[target],{'date_done':picks[p]['date_done']}],{'context':{'tz':'UTC'}})
  for r in group:
   m.mutate('stock.move','write',[[r['target_move']],{'date':r['date']}],{'context':{'tz':'UTC'}});m.mutate('stock.move.line','write',[r['target_lines'],{'date':r['date']}],{'context':{'tz':'UTC'}})
   actual=m.b.read('stock.move.line',r['target_lines'],['quantity','lot_id','product_id','location_id','location_dest_id','state','date']);req(all(x['state']=='done' and x['date']==r['date'] for x in actual),'Date/state mismatch')
   expected=sorted((m.effective_qty(x),m.maps['stock.lot'].get(rid(x['lot_id']),False)) for x in lines[r['source_move']]);got=sorted((x['quantity'],rid(x['lot_id'])) for x in actual);req(expected==got,'Lot/quantity changed')
   r.update(status='verified',target_qty=sum(x['quantity'] for x in actual),after_lines=actual)
  m.persist();print(json.dumps({'source_picking':p,'target_picking':target,'verified_moves':len(group)}),flush=True)
 m.j['old_po_receipt_exceptions']=issues;m.persist();save(m.path.parent/'all-old-po-receipts-report.json',{'records':records,'exceptions':issues});print('Finished standalone old PO receipts',flush=True)
if __name__=='__main__':main()
