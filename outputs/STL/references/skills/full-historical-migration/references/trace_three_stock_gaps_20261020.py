"""Read-only root cause for DP145, BLANK PVC and LANYARD HEAT TRANSFER."""
import json,runpy,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-sue-stock-review-20261020'
socket.setdefaulttimeout(60)
Reader=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']
result={'writes_performed':False}
for side,env,ids in [('source','v14-prod',[43594,51469,51470]),('target','v19-staging',[113358,112635,114965])]:
 r=Reader(ROOT/f'mcp-server-odoo/envs/{env}/.env')
 if side=='target':assert r.db=='py19-staging-39654560'
 schema=r.call('stock.move','fields_get',[],{'attributes':['type']})
 fs=[x for x in ['name','reference','origin','date','create_date','write_date','state','product_id','product_uom','quantity_done','quantity','location_id','location_dest_id','inventory_id','picking_id','move_line_ids','sale_line_id','production_id','raw_material_production_id'] if x in schema]
 moves=r.search_read('stock.move',[['company_id','=',1],['product_id','in',ids],['state','=','done']],fs)
 fields=['move_id','product_id','product_uom_id','date','lot_id','location_id','location_dest_id','qty_done' if side=='source' else 'quantity']
 lines=r.read('stock.move.line',[i for m in moves for i in m['move_line_ids']],fields)
 locs=r.search_read('stock.location',[['usage','in',['internal','transit']],'|',['company_id','=',1],['company_id','=',False]],['complete_name','usage'])
 quantities={}
 for label,date in [('opening','2026-06-30 15:59:59'),('closing','2026-07-31 15:00:00')]:
  quantities[label]=r.call('product.product','read',[ids],{'fields':['name','qty_available'],'context':{'to_date':date,'location':[x['id'] for x in locs],'compute_child':False,'force_company':1}})
 data={'moves':moves,'lines':lines,'locations':locs,'quantities':quantities}
 if side=='source':
  qs=r.call('stock.quant','fields_get',[],{'attributes':['type','string']})
  qfs=[f for f in ['product_id','location_id','lot_id','quantity','inventory_quantity','inventory_diff_quantity','inventory_quantity_set','write_date'] if f in qs]
  data['quant_field_metadata']={f:qs[f] for f in qfs}
  data['current_quants']=r.search_read('stock.quant',[['product_id','in',ids],['company_id','=',1]],qfs)
  inv_ids=sorted({m['inventory_id'][0] for m in moves if m.get('inventory_id')})
  data['inventories']=r.read('stock.inventory',inv_ids,['name','date','state','create_date','write_date'])
  data['inventory_lines']=[x for x in r.search_read('stock.inventory.line',[['product_id','in',ids]],['inventory_id','product_id','location_id','prod_lot_id','product_qty','theoretical_qty','create_date','write_date']) if x['product_id'][0] in ids]
 result[side]=data
 (OUT/'three-products-full-history.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(side,'moves',len(moves),'lines',len(lines),'quantities',json.dumps(quantities,ensure_ascii=True),flush=True)
