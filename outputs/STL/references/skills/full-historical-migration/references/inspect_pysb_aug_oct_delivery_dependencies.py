"""Read-only commercial and procurement dependencies before any SO confirmation."""
import json
import runpy
from pathlib import Path
I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def load(n):return json.loads((I['OUT']/n).read_text(encoding='utf8'))

def main():
    maps=load('discovery-manifest.json')['maps'];lines=load('verify-source-sale.order.line.json')
    ids=sorted({rid(x['order_id']) for x in lines});lids=[x['id'] for x in lines]
    a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    headerfields='name state company_id partner_id partner_invoice_id partner_shipping_id currency_id warehouse_id date_order order_line picking_ids invoice_ids amount_untaxed amount_tax amount_total write_date pricelist_id'.split()
    linefields='order_id display_type product_id product_uom product_uom_id product_uom_qty qty_delivered qty_invoiced price_unit discount tax_id tax_ids price_subtotal price_total route_id move_ids invoice_lines write_date'.split()
    source=a.read('sale.order',ids,headerfields);sl=a.read('sale.order.line',lids,linefields)
    target=b.read('sale.order',[maps.get('sale.order',{}).get(str(i)) for i in ids],headerfields)
    tl=b.read('sale.order.line',[i for x in target for i in x['order_line']],linefields)
    products=b.read('product.product',sorted({rid(x['product_id']) for x in tl if x['product_id']}),['active','type','is_storable','tracking','route_ids','categ_id','service_tracking','uom_id'])
    categories=b.read('product.category',sorted({rid(x['categ_id']) for x in products}),['route_ids'])
    routeids=sorted({i for x in products+categories for i in x['route_ids']})
    routes=b.read('stock.route',routeids,['name','rule_ids','company_id','active'])
    rules=b.read('stock.rule',[i for x in routes for i in x['rule_ids']],['name','action','procure_method','location_src_id','location_dest_id','picking_type_id','route_id'])
    for name,rows in [('source-delivery-orders',source),('source-delivery-order-lines',sl),('target-delivery-orders',target),('target-delivery-order-lines',tl),('target-delivery-products',products),('target-delivery-categories',categories),('target-delivery-routes',routes),('target-delivery-rules',rules)]:I['save'](name+'.json',rows)
    print(json.dumps({'source_orders':len(source),'target_orders':len(target),'source_lines':len(sl),'target_lines':len(tl),'routes':len(routes),'rules':len(rules)}),flush=True)

if __name__=='__main__':main()
