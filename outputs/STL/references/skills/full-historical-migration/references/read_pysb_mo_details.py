"""Read source MO execution and target dependencies; company 1 only."""
import json,runpy,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
def main():
 socket.setdefaulttimeout(90)
 a=H['Reader'](ROOT/'mcp-server-odoo/envs/v14-prod/.env');b=H['Reader'](ROOT/'mcp-server-odoo/envs/v19-staging/.env')
 H['require'](b.db=='py19-staging-39654560' and a.db=='paoyeang_live','Wrong DB')
 schemas={model:a.call(model,'fields_get',[],{'attributes':['type','store','relation']}) for model in ['mrp.production','stock.move','stock.move.line']}
 fields=['name','company_id','state','date_start','date_planned_start','date_finished','date_planned_finished','product_id','product_qty','product_uom_id','move_raw_ids','move_finished_ids','origin','location_src_id','location_dest_id','picking_type_id','lot_producing_id','bom_id']
 fields += [k for k in schemas['mrp.production'] if any(w in k.lower() for w in ['reference','ref_no','ref_number']) and k not in fields and schemas['mrp.production'][k]['type'] in ['char','text']]
 fields=[k for k in fields if k in schemas['mrp.production']]
 mo=a.search_read('mrp.production',[['company_id','=',1],['state','=','done'],['date_finished','>=','2026-06-30 16:00:00'],['date_finished','<','2026-07-31 16:00:00']],fields)
 H['require'](len(mo)==516,'MO scope changed')
 print('MO read',len(mo),fields,flush=True)
 mf=['name','state','company_id','picking_id','sale_line_id','purchase_line_id','product_id','product_uom','product_uom_qty','quantity_done','location_id','location_dest_id','move_orig_ids','move_dest_ids','move_line_ids','origin_returned_move_id','returned_move_ids','date','raw_material_production_id','production_id','to_refund','scrapped']
 moves=a.read('stock.move',[i for x in mo for k in ['move_raw_ids','move_finished_ids'] for i in x[k]],[k for k in mf if k in schemas['stock.move']])
 print('MO moves',len(moves),flush=True)
 lf=['move_id','picking_id','company_id','product_id','product_uom_id','qty_done','lot_id','lot_name','location_id','location_dest_id','date','owner_id','package_id','result_package_id','state']
 lines=a.read('stock.move.line',[i for x in moves for i in x['move_line_ids']],[k for k in lf if k in schemas['stock.move.line']])
 print('MO lines',len(lines),flush=True)
 pids={x['product_id'][0] for x in moves}
 products=a.read('product.product',pids,['name','default_code','barcode','type','tracking','uom_id','packing_ratio','active'])
 lots=a.read('stock.production.lot',{x['lot_id'][0] for x in lines if x['lot_id']},['name','product_id','company_id'])
 codes=list({x['default_code'] for x in products if x['default_code']})
 targets=[]
 for start in range(0,len(codes),300):targets+=b.search_read('product.product',[['default_code','in',codes[start:start+300]]],['name','default_code','barcode','tracking','uom_id','packing_ratio','active'])
 data={'mo':mo,'moves':moves,'lines':lines,'products':products,'lots':lots,'target_products':targets,'source_schema':schemas,
 'target_mo_schema':b.call('mrp.production','fields_get',[],{'attributes':['type','store','readonly','relation']}),
 'transfer_move_flags':a.read('stock.move',[x['id'] for x in json.loads((OUT/'v14-prod-snapshot.json').read_text(encoding='utf8'))['moves']]+[x['id'] for x in json.loads((OUT/'v14-prod-snapshot.json').read_text(encoding='utf8'))['chain_moves']],['to_refund','scrapped']),
 'target_mo':b.search_read('mrp.production',[['company_id','=',1]],['name','state','company_id','product_id'])}
 H['save'](OUT/'mo-details.json',data)
 print(json.dumps({'mo':len(mo),'moves':len(moves),'lines':len(lines),'products':len(products),'lots':len(lots),'target_mo':len(data['target_mo'])}),flush=True)
if __name__=='__main__':main()
