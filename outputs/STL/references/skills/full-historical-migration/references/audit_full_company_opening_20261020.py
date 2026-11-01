"""Full-company July opening audit, read-only. Includes shared/archived products."""
import json,runpy,socket,argparse
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-opening-full-audit-20261020';OUT.mkdir(exist_ok=True)
socket.setdefaulttimeout(90)
Reader=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']
CUTOFF='2026-06-30 15:59:59'
def save(name,x):
 p=OUT/name;tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(p)
def read_side(side,env):
 r=Reader(ROOT/f'mcp-server-odoo/envs/{env}/.env')
 if side=='target':assert (r.url,r.db)==('https://py-staging.odoo.com','py19-staging-39654560')
 locs=r.search_read('stock.location',[['usage','in',['internal','transit']],'|',['company_id','=',1],['company_id','=',False]],['complete_name','usage','company_id'])
 schema=r.call('product.product','fields_get',[],{'attributes':['type']})
 fs=[f for f in ['name','display_name','default_code','barcode','active','company_id','uom_id','type','is_storable','tracking','product_tmpl_id','create_date'] if f in schema]
 products=r.search_read('product.product',['|',['company_id','=',1],['company_id','=',False]],fs)
 quantities=[]
 for n in range(0,len(products),400):
  batch=products[n:n+400]
  quantities+=r.call('product.product','read',[[p['id'] for p in batch]],{'fields':['qty_available'],'context':{'to_date':CUTOFF,'location':[x['id'] for x in locs],'compute_child':False,'force_company':1}})
  print(json.dumps({'side':side,'phase':'quantities','read':min(n+400,len(products)),'total':len(products)}),flush=True)
 result={'database':r.db,'checked_utc':datetime.now(timezone.utc).isoformat(),'cutoff_utc':CUTOFF,'locations':locs,'products':products,'quantities':quantities,'writes_performed':False}
 if side=='target':
  sf=r.call('stock.move','fields_get',[],{'attributes':['type']})
  fields=[x for x in ['reference','inventory_name','origin','product_id','product_uom','quantity','product_uom_qty','date','state','location_id','location_dest_id','move_line_ids','is_inventory'] if x in sf]
  result['original_opening_moves']=r.search_read('stock.move',[['company_id','=',1],['state','=','done'],['reference','=','Opening Balance']],fields)
  result['uoms']=r.search_read('uom.uom',[],['name','factor','rounding'])
 save(side+'-opening-snapshot.json',result)
 return {'side':side,'products':len(products),'nonzero':sum(abs(x['qty_available'])>0.000001 for x in quantities),'opening_moves':len(result.get('original_opening_moves',[]))}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--side',choices=['source','target','both'],default='both');a=parser.parse_args()
 jobs=[('source','v14-prod'),('target','v19-staging')]
 with ThreadPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(read_side,s,e) for s,e in jobs if a.side in [s,'both']]
  for f in futures:print(json.dumps(f.result()),flush=True)
if __name__=='__main__':main()
