"""Read-only evidence for new full-company opening audit findings."""
import json,runpy,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-opening-full-audit-20261020'
socket.setdefaulttimeout(60)
Reader=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']
result={'writes_performed':False}
for side,env,ids in [('source','v14-prod',[46247,46317,51399,52942,54750,46982]),('target','v19-staging',[119904,114673,114672,113125,116792])]:
 r=Reader(ROOT/f'mcp-server-odoo/envs/{env}/.env');schema=r.call('stock.move','fields_get',[],{'attributes':['type']})
 fs=[x for x in ['reference','origin','date','create_date','write_date','product_id','quantity','quantity_done','product_uom','location_id','location_dest_id','picking_id','move_line_ids','inventory_id'] if x in schema]
 moves=r.search_read('stock.move',[['company_id','=',1],['state','=','done'],['product_id','in',ids]],fs)
 q=r.search_read('stock.quant',[['product_id','in',ids]],['product_id','quantity','reserved_quantity','location_id','lot_id','company_id'])
 locids=sorted({x['location_id'][0] for x in q}|{x[f][0] for x in moves for f in ['location_id','location_dest_id']})
 meta=r.call('product.product','fields_get',[],{'attributes':['type']})
 products=r.read('product.product',ids,[x for x in ['name','barcode','default_code','uom_id','type','is_storable','qty_available','create_date'] if x in meta])
 result[side]={'moves':moves,'quants':q,'locations':r.read('stock.location',locids,['usage','complete_name','company_id']),'products':products}
 (OUT/'finding-source-target-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(side,'moves',len(moves),'quants',len(q),flush=True)
