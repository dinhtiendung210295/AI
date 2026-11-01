"""Resolve MO dependencies read-only, generate execution manifest."""
import json,runpy,socket
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def main():
 socket.setdefaulttimeout(90);a=load('v14-prod-snapshot.json');b=load('v19-staging-snapshot.json');p=load('stock-preparation-plan.json');mo=load('mo-details.json')
 r=H['Reader'](ROOT/'mcp-server-odoo/envs/v19-staging/.env');H['require'](r.db=='py19-staging-39654560','Wrong target')
 M=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['TargetMapper']
 mapper=M(r);mapped=mapper.products(mo['products'])
 for s,t in mapped.items():
  H['require'](p['maps']['product.product'].get(str(s),t)==t,'Product mapping changed')
  p['maps']['product.product'][str(s)]=t
 targets=r.read('product.product',set(p['maps']['product.product'].values()),['name','default_code','barcode','tracking','uom_id','packing_ratio','active'])
 ti={x['id']:x for x in targets}
 problems=list(mapper.exceptions)
 for s in mo['products']:
  tid=mapped.get(s['id'])
  if tid:
   t=ti[tid];su=s['uom_id'];tu=t['uom_id']
   if s['tracking']!=t['tracking']:problems.append({'scope':'product.product','source_id':s['id'],'reason':'tracking_mismatch','source':s['tracking'],'target':t['tracking']})
   if {'UNIT':'Units','KG':'kg','GRAM':'g'}.get(su[1],su[1]).casefold()!=tu[1].casefold():problems.append({'scope':'product.product','source_id':s['id'],'reason':'base_uom_mismatch','source':su,'target':tu})
   else:p['maps']['uom.uom'][str(su[0])]=tu[0]
 # v19 already routes these transactions through its existing Consignment type.
 # Retain that configured code; compare stock directions by actual locations.
 for s in a['picking_types']:
  if str(s['id']) in p['maps'].get('stock.picking.type',{}):continue
  matches=[t for t in b['picking_types'] if t['name']==s['name'] and t['warehouse_id'] and t['warehouse_id'][0]==p['maps']['stock.warehouse'].get(str(s['warehouse_id'][0]))] if s['warehouse_id'] else []
  if len(matches)==1:
   p['maps']['stock.picking.type'][str(s['id'])]=matches[0]['id']
   p.setdefault('configuration_aliases',[]).append({'source_type':s,'target_type':matches[0]})
 required_products={x['product_id'][0] for x in mo['moves']};badproducts={x['source_id'] for x in problems if x.get('scope')=='product.product'}
 p['mo_exceptions']=problems
 p['blocked_mo']=[x['id'] for x in mo['mo'] if any(m['product_id'][0] in badproducts for m in mo['moves'] if m['id'] in x['move_raw_ids']+x['move_finished_ids'])]
 p['exceptions']=[x for x in p['exceptions'] if not(x['type']=='missing_mapping' and str(x['id']) in p['maps'].get(x['model'],{}))]
 lots={x['id']:x for x in a['lots']+mo['lots']};tlots=load('v19-staging-dependencies.json')['lots'];lookup={}
 for t in tlots:lookup.setdefault((t['product_id'][0],t['name']),[]).append(t['id'])
 p['lot_plan']=[]
 for s in lots.values():
  tid=p['maps']['product.product'].get(str(s['product_id'][0]));hits=lookup.get((tid,s['name']),[])
  p['lot_plan'].append({'source_id':s['id'],'product_id':tid,'name':s['name'],'target_id':hits[0] if len(hits)==1 else False,'status':'existing' if len(hits)==1 else ('create' if len(hits)==0 and tid else 'exception')})
 p['target_products']=targets
 H['save'](OUT/'execution-manifest.json',p)
 print(json.dumps({'MO_products':len(mo['products']),'mapped':len(mapped),'MO_exceptions':problems,'blocked_mo':len(p['blocked_mo']),'lot_status':dict(Counter(x['status'] for x in p['lot_plan'])),'remaining_transfer_exceptions':p['exceptions']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
