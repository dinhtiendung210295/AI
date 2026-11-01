"""Read-only dependencies for actual posted v14 inventory adjustments."""
import json
import argparse
import runpy
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
OUT=I['OUT']
def load(name):return json.loads((OUT/name).read_text(encoding='utf8'))
def rid(value):return value[0] if isinstance(value,(list,tuple)) and value else value or False


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--refresh-target-lots-only',action='store_true');args=parser.parse_args()
    if args.refresh_target_lots_only:
        b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
        lots=load('source-inventory-adjustment-lots.json');products=load('target-inventory-adjustment-products.json')
        target_lots=b.scan('stock.lot',[['company_id','=',1],['product_id','in',[x['id'] for x in products]],['name','in',[x['name'] for x in lots]]],['name','product_id','company_id','expiration_date','use_date','removal_date','alert_date'])
        I['save']('target-inventory-adjustment-lots.json',target_lots)
        print(json.dumps({'refreshed_target_lot_candidates':len(target_lots),'source_snapshots_unchanged':True}),flush=True);return
    categories={x['source_move_id']:x['category'] for x in load('after-run-stock-coverage.json')['results']}
    moves=[x for x in load('source-moves.json') if categories[x['id']]=='inventory_adjustment']
    a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'))
    b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    headers=a.read('stock.inventory',[rid(x['inventory_id']) for x in moves if x['inventory_id']],['name','state','date','accounting_date','company_id','line_ids','move_ids','write_date'])
    lines=a.read('stock.inventory.line',[i for x in headers for i in x['line_ids']],['inventory_id','product_id','product_uom_id','location_id','prod_lot_id','package_id','partner_id','product_qty','theoretical_qty','write_date'])
    frozen_ids={x['id'] for x in load('source-moves.json')}
    extra=a.read('stock.move',[i for x in headers for i in x['move_ids'] if i not in frozen_ids],['state','date','product_id','quantity_done','company_id'])
    I['save']('source-inventory-adjustment-extra-moves.json',extra)
    I['save']('source-inventory-adjustment-headers.json',headers);I['save']('source-inventory-adjustment-count-lines.json',lines)
    maps=load('after-run-stock-mapping.json')['maps']
    product_ids=[maps.get('product.product',{}).get(str(rid(x['product_id']))) for x in moves]
    products=b.read('product.product',product_ids,['name','uom_id','tracking','is_storable','property_stock_inventory','company_id','active'])
    I['save']('target-inventory-adjustment-products.json',products)
    mids={x['id'] for x in moves};source_lines=[x for x in load('source-move-lines.json') if rid(x['move_id']) in mids]
    lots=a.read('stock.production.lot',[rid(x['lot_id']) for x in source_lines if x['lot_id']],['name','product_id','company_id','expiration_date','use_date','removal_date','alert_date','write_date'])
    I['save']('source-inventory-adjustment-lots.json',lots)
    target_lots=b.scan('stock.lot',[['company_id','=',1],['product_id','in',[x['id'] for x in products]],['name','in',[x['name'] for x in lots]]],['name','product_id','company_id','expiration_date','use_date','removal_date','alert_date'])
    I['save']('target-inventory-adjustment-lots.json',target_lots)
    print(json.dumps({'source_moves':len(moves),'inventory_headers':len(headers),'count_lines':len(lines),'target_products':len(products),'lots':len(lots)}),flush=True)


if __name__=='__main__':main()
