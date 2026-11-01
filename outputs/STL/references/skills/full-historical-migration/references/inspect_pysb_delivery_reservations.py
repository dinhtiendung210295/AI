"""Read-only exact quant and reservation ownership for a staged delivery."""
import argparse,json,runpy
from pathlib import Path
BASE=Path(__file__).parent
M=runpy.run_path(str(BASE/'migrate_pysb_independent_deliveries.py'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--source-so',type=int,required=True);a=p.parse_args()
    r=M['Run']();rec=r.j['groups'][str(a.source_so)];mids=list(rec['move_pairs'].values())
    fields='company_id picking_id move_id product_id product_uom_id quantity picked state location_id location_dest_id lot_id package_id owner_id'.split()
    own=r.b.scan('stock.move.line',[['move_id','in',mids]],fields)
    products={M['rid'](x['product_id']) for x in own};locations={M['rid'](x['location_id']) for x in own};lots={M['rid'](x['lot_id']) for x in own}
    quants=r.b.scan('stock.quant',[['company_id','=',1],['product_id','in',list(products)],['location_id','in',list(locations)],['lot_id','in',list(lots)],['package_id','=',False],['owner_id','=',False]],['product_id','location_id','lot_id','quantity','reserved_quantity'])
    reservations=r.b.scan('stock.move.line',[['company_id','=',1],['product_id','in',list(products)],['location_id','in',list(locations)],['lot_id','in',list(lots)],['state','not in',['done','cancel']],['quantity','>',0]],fields)
    moves=r.b.read('stock.move',{M['rid'](x['move_id']) for x in reservations},['state','company_id','picking_id','sale_line_id','purchase_line_id','raw_material_production_id','production_id','origin','product_id','product_uom_qty','quantity','picked'])
    picks=r.b.read('stock.picking',{M['rid'](x['picking_id']) for x in reservations if x['picking_id']},['state','company_id','sale_id','origin','move_ids'])
    confirmation=M['load']('phases/so-confirmation-journal.json')['orders']
    known={x['target_id']:int(sid) for sid,x in confirmation.items() if x['status']=='verified_confirmed'}
    evidence=dict(source_so=a.source_so,stage=rec['phase'],own_lines=own,quants=quants,reservations=reservations,moves=moves,pickings=picks,scoped_confirmed_owners={p['id']:known.get(M['rid'](p['sale_id'])) for p in picks},uncertain_operations=r.uncertain)
    M['save']('delivery-'+str(a.source_so)+'-reservation-readback.json',evidence)
    print(json.dumps(evidence,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
