"""Read-only inventory of pre-July POs with completed receipts from July onward."""
import runpy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/complete_pysb_stock_migration.py'))
def main():
 m=H['Completion']();rid=H['rid'];save=H['H']['save']
 pos=m.a.search_read('purchase.order',[['company_id','=',1],['date_order','<','2026-06-30 16:00:00']],['name','date_order','state','order_line','partner_id'])
 lids=[i for p in pos for i in p['order_line']]
 fields=['name','date','state','company_id','product_id','product_uom','product_uom_qty','location_id','location_dest_id','picking_id','move_line_ids','move_orig_ids','move_dest_ids','purchase_line_id']
 moves=m.a.search_read('stock.move',[['company_id','=',1],['state','=','done'],['purchase_line_id','in',lids],['date','>=','2026-06-30 16:00:00']],fields)
 locations={x['id']:x for x in m.a.search_read('stock.location',[],['usage','complete_name'])}
 roots=[x for x in moves if locations[rid(x['location_id'])]['usage']=='supplier' and locations[rid(x['location_dest_id'])]['usage']=='internal']
 found={x['id']:x for x in roots};front=roots
 for _ in range(20):
  ids={i for x in front for i in x['move_dest_ids']}-set(found)
  if not ids:break
  nextrows=m.a.read('stock.move',sorted(ids),fields)
  front=[x for x in nextrows if x['state']=='done' and rid(x['company_id'])==1 and x['date']>='2026-06-30 16:00:00' and locations[rid(x['location_id'])]['usage']=='internal' and locations[rid(x['location_dest_id'])]['usage'] in ['internal','supplier']]
  found.update({x['id']:x for x in front})
 # Some v14 Input→Stock moves have broken move_dest_ids. Include the exact
 # source move name PO prefix and only internal movements belonging to old POs.
 names={p['name'] for p in pos}
 supplied=H['load']('remaining-150-missing-supply-evidence.json')
 extra={x['move_id'][0] for row in supplied for x in row['missing_prior_inputs'] if x['move_id'][1].split('/')[0] in names}-set(found)
 if extra:found.update({x['id']:x for x in m.a.read('stock.move',sorted(extra),fields)})
 lines=m.a.read('stock.move.line',[i for x in found.values() for i in x['move_line_ids']],['move_id','product_id','product_uom_id','qty_done','lot_id','location_id','location_dest_id','package_id','result_package_id','owner_id','date'])
 picks=m.a.read('stock.picking',sorted({rid(x['picking_id']) for x in found.values() if x['picking_id']}),['name','date_done','origin','partner_id','company_id','state','picking_type_id'])
 existing={int(k):v for k,v in m.maps['stock.move'].items()};existing.update({x['source_move']:x['target_move'] for x in m.j.get('standalone_source_receipts',[]) if x['status']=='verified'})
 output={'database':m.a.db,'company_id':1,'cutoff_utc':'2026-06-30 16:00:00','date_end':None,'old_pos':pos,'roots':[x['id'] for x in roots],'moves':list(found.values()),'lines':lines,'pickings':picks,'locations':list(locations.values()),'already_mapped':existing,'summary':{'old_pos':len(pos),'receipt_roots':len(roots),'moves':len(found),'pickings':len(picks),'missing_moves':sum(i not in existing for i in found),'latest_move_date':max((x['date'] for x in found.values()),default=None)}}
 save(m.path.parent/'old-po-late-receipts-discovery.json',output);print(json.dumps(output['summary']),flush=True)
if __name__=='__main__':main()
