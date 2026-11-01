"""Read-only dependencies for company-1 historical stock migration."""
import runpy,json,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
R,save,require=[H[k] for k in ['Reader','save','require']]
OUT=ROOT/'outputs/pysb-stock-migration-20261012'
def main():
 socket.setdefaulttimeout(90)
 for version in ['v14-prod','v19-staging']:
  r=R(ROOT/f'mcp-server-odoo/envs/{version}/.env');d=json.loads((OUT/f'{version}-snapshot.json').read_text(encoding='utf8'));s=version=='v14-prod'
  data={}
  so=json.loads((ROOT/'outputs/pysb-so-confirm-20261012-staging/so-delivery-handoff.json').read_text(encoding='utf8'))
  po=json.loads((ROOT/'outputs/pysb-po-confirm-20261012-staging/po-receipt-handoff.json').read_text(encoding='utf8'))
  data['so']=r.read('sale.order',[x['source_id' if s else 'target_id'] for x in so],['name','company_id','partner_id','partner_shipping_id','warehouse_id','order_line'])
  data['po']=r.read('purchase.order',[x['v14_id' if s else 'v19_id'] for x in po],['name','company_id','partner_id','order_line'])
  data['pol']=r.read('purchase.order.line',[i for x in data['po'] for i in x['order_line']],['order_id','product_id','product_uom' if s else 'product_uom_id','product_qty'])
  print(version,'orders read',flush=True)
  products=set(x['product_id'][0] for x in d['moves']+d['chain_moves'] if x['product_id'])
  pf=r.call('product.product','fields_get',[],{'attributes':['type']})
  data['products']=r.read('product.product',products,[k for k in ['name','default_code','barcode','company_id','type','is_storable','tracking','uom_id','packing_ratio','active'] if k in pf])
  uf=r.call('uom.uom','fields_get',[],{'attributes':['type']})
  data['uoms']=r.search_read('uom.uom',[],[k for k in ['name','factor','factor_inv','relative_factor','relative_uom_id','category_id','rounding','uom_type'] if k in uf])
  data['quants']=r.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','owner_id','package_id','quantity','reserved_quantity'])
  print(version,'masters/quants read',flush=True)
  lotm='stock.production.lot' if s else 'stock.lot'
  if not s:
   data['lots']=r.search_read(lotm,[['company_id','=',1]],['name','product_id','company_id'])
   data['packages']=r.search_read('stock.package',[['company_id','=',1]],['name','company_id'])
  else:
   pids=set(x[k][0] for x in d['move_lines']+d['chain_move_lines'] for k in ['package_id','result_package_id'] if x[k])
   data['packages']=r.read('stock.quant.package',pids,['name','company_id'])
   data['repack_recent']=r.call('repacking.order','search_read',[[['company_id','=',1]]],{'fields':['name','state','date_confirm','date_complete'],'order':'id desc','limit':15})
  mf=r.call('mrp.production','fields_get',[],{'attributes':['type']})
  datefield='date_finished'
  data['mo_july']=r.search_read('mrp.production',[['company_id','=',1],[datefield,'>=','2026-06-30 16:00:00'],[datefield,'<','2026-07-31 16:00:00']],[k for k in ['name','company_id','state','date_start','date_planned_start','date_finished','product_id','product_qty','product_uom_id','move_raw_ids','move_finished_ids','origin'] if k in mf])
  save(OUT/f'{version}-dependencies.json',data)
  print(json.dumps({'version':version,'products':len(data['products']),'quants':len(data['quants']),'mo_july':len(data['mo_july']),'lots':len(data.get('lots',[]))}),flush=True)
if __name__=='__main__':main()
