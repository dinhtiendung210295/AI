"""Offline mapping and exception report; no Odoo writes."""
import json,runpy
from collections import defaultdict,Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
def load(name):return json.loads((OUT/name).read_text(encoding='utf8'))
def rid(v):return v[0] if isinstance(v,list) and v else v or False
def idx(rows):return {x['id']:x for x in rows}
def main():
 a,b=load('v14-prod-snapshot.json'),load('v19-staging-snapshot.json');ad,bd=load('v14-prod-dependencies.json'),load('v19-staging-dependencies.json')
 ext=defaultdict(dict)
 for x in b['external_ids']:
  prefix=x['model'].replace('.','_')+'_'
  if x['name'].startswith(prefix):ext[x['model']][int(x['name'][len(prefix):])]=x['res_id']
 issues=[];maps={'sale.order.line':ext['sale.order.line'],'purchase.order.line':ext['purchase.order.line'],'sale.order':ext['sale.order'],'purchase.order':ext['purchase.order']}
 def add(model,s,t):
  if s and t:
   H['require'](maps.setdefault(model,{}).get(s,t)==t,f'Inconsistent mapping {model} {s}')
   maps[model][s]=t
 for model,srows,trows,uomfield in [('sale.order.line',a['sol'],b['sol'],'product_uom'),('purchase.order.line',ad['pol'],bd['pol'],'product_uom')]:
  ti=idx(trows)
  for s in srows:
   t=ti[maps[model][s['id']]]
   add('product.product',rid(s['product_id']),rid(t['product_id']))
   add('uom.uom',rid(s.get(uomfield)),rid(t.get('product_uom_id')))
 for model in ['so','po']:
  em='sale.order' if model=='so' else 'purchase.order';ti=idx(bd[model])
  for s in ad[model]:
   t=ti[maps[em][s['id']]]
   for field in ['partner_id','warehouse_id']:
    add('stock.warehouse' if field=='warehouse_id' else 'res.partner',rid(s.get(field)),rid(t.get(field)))
 for s in a['locations']:
  matches=[t for t in b['locations'] if t['complete_name']==s['complete_name'] and t['usage']==s['usage']]
  if s['id'] in ext['stock.location']:matches=[t for t in b['locations'] if t['id']==ext['stock.location'][s['id']]]
  if not matches and s['usage'] in ['supplier','customer','production','inventory']:matches=[t for t in b['locations'] if t['usage']==s['usage']]
  if len(matches)==1:add('stock.location',s['id'],matches[0]['id'])
 for s in a['picking_types']:
  matches=[t for t in b['picking_types'] if t['name']==s['name'] and t['code']==s['code'] and rid(t['warehouse_id'])==maps.get('stock.warehouse',{}).get(rid(s['warehouse_id']))]
  if len(matches)==1:add('stock.picking.type',s['id'],matches[0]['id'])
 for s in a['routes']:
  matches=[t for t in b['routes'] if t['name']==s['name']]
  if s['id'] in ext['stock.route']:matches=[t for t in b['routes'] if t['id']==ext['stock.route'][s['id']]]
  if len(matches)==1:add('stock.route',s['id'],matches[0]['id'])
 for s in ad['uoms']:
  if s['id'] in maps.get('uom.uom',{}):continue
  matches=[t for t in bd['uoms'] if t['name']=={'UNIT':'Units'}.get(s['name'],s['name'])]
  if len(matches)==1:add('uom.uom',s['id'],matches[0]['id'])
 bi=idx(b['sol']);routecheck=[]
 for s in a['sol']:
  t=bi[maps['sale.order.line'][s['id']]];expected=[maps['stock.route'].get(rid(s['route_id']))] if s['route_id'] else []
  result={'source_line':s['id'],'target_line':t['id'],'source_route':s['route_id'],'target_routes':t['route_ids'],'match':sorted(expected)==sorted(t['route_ids'])}
  routecheck.append(result)
  if not result['match']:issues.append({'type':'route_mismatch',**result})
 sm=idx(a['moves']+a['chain_moves']);sp=idx(a['pickings']+a['chain_pickings']);byline=defaultdict(list)
 inherited={i:{field:({rid(m.get(field))} if m.get(field) else set()) for field in ['sale_line_id','purchase_line_id']} for i,m in sm.items()}
 for _ in range(8):
  changed=False
  for i,m in sm.items():
   for j in m['move_orig_ids']+m['move_dest_ids']:
    if j not in sm or rid(sm[j]['product_id'])!=rid(m['product_id']):continue
    for field in ['sale_line_id','purchase_line_id']:
     if m.get(field):continue
     new=inherited[i][field]|inherited[j][field]
     if new!=inherited[i][field]:inherited[i][field]=new;changed=True
  if not changed:break
 for m in sm.values():
  for field in ['sale_line_id','purchase_line_id']:
   if len(inherited[m['id']][field])==1:byline[(field,next(iter(inherited[m['id']][field])))].append(m)
 inv={model:{t:s for s,t in mapping.items()} for model,mapping in maps.items()}
 reuse={};used=set()
 for t in b['moves']:
  candidates=[]
  for field,model in [('sale_line_id','sale.order.line'),('purchase_line_id','purchase.order.line')]:
   sid=inv[model].get(rid(t.get(field)))
   if sid:
    candidates.extend(m for m in byline[field,sid] if m['id'] not in used and not m['origin_returned_move_id'] and maps['product.product'].get(rid(m['product_id']))==rid(t['product_id']) and maps['stock.location'].get(rid(m['location_dest_id']))==rid(t['location_dest_id']))
  if candidates:
   exact=[m for m in candidates if maps['stock.location'].get(rid(m['location_id']))==rid(t['location_id'])]
   choices=exact or candidates
   m=min(choices,key=lambda x:x['id'])
   if m['id'] in used:issues.append({'type':'ambiguous_existing_move','target':t['id'],'source':m['id']})
   else:reuse[m['id']]=t['id'];used.add(m['id'])
  else:issues.append({'type':'unmatched_existing_move','target':t['id'],'product':t['product_id'],'sale_line':t['sale_line_id'],'purchase_line':t['purchase_line_id']})
 for p in sp.values():
  for field,model in [('location_id','stock.location'),('location_dest_id','stock.location'),('picking_type_id','stock.picking.type')]:
   if rid(p[field]) not in maps.get(model,{}):issues.append({'type':'missing_mapping','model':model,'id':rid(p[field]),'picking_id':p['id'],'reference':p['name'],'state':p['state'],'date_done':p['date_done']})
 for m in sm.values():
  for field,model in [('product_id','product.product'),('product_uom','uom.uom'),('location_id','stock.location'),('location_dest_id','stock.location')]:
   if rid(m[field]) not in maps.get(model,{}):issues.append({'type':'missing_mapping','model':model,'id':rid(m[field]),'move_id':m['id'],'reference':sp[rid(m['picking_id'])]['name'] if m['picking_id'] else False,'state':m['state']})
 lotplan=[];lots=defaultdict(list)
 for t in bd['lots']:lots[(rid(t['product_id']),t['name'])].append(t['id'])
 for s in a['lots']:
  tp=maps['product.product'].get(rid(s['product_id']));matches=lots[(tp,s['name'])] if tp else []
  lotplan.append({'source_id':s['id'],'product_id':tp,'name':s['name'],'target_id':matches[0] if len(matches)==1 else False,'status':'existing' if len(matches)==1 else ('create' if not matches and tp else 'exception')})
  if len(matches)>1 or not tp:issues.append({'type':'lot_mapping','source':s['id'],'name':s['name'],'matches':matches,'product':s['product_id']})
 plan={'company_id':1,'target_database':b['database'],'maps':maps,'reuse_moves':reuse,'lot_plan':lotplan,'route_check':routecheck,'exceptions':issues,
 'summary':{'routes_checked':len(routecheck),'route_mismatches':sum(not x['match'] for x in routecheck),'reuse_moves':len(reuse),'target_moves':len(b['moves']),'source_pickings':len(sp),'source_moves':len(sm),'lot_status':dict(Counter(x['status'] for x in lotplan)),'exception_types':dict(Counter(x['type'] for x in issues))}}
 H['save'](OUT/'stock-preparation-plan.json',plan)
 print(json.dumps(plan['summary'],ensure_ascii=False,indent=2))
 print(json.dumps(issues[:20],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
