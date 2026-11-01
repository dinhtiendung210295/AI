"""Read-only evidence for Bruce-authorized SO remediation on both production DBs."""
import runpy
import json
from pathlib import Path
BASE = Path(__file__).parent
M = runpy.run_path(str(BASE / 'confirm_pysb_prod_so.py'))
OUT = M['I']['OUT']; rid = M['rid']; save = M['save']; load = M['load']
DEST = OUT / 'so-remediation'


def main():
    DEST.mkdir(exist_ok=True)
    lock = runpy.run_path(str(BASE / 'production_write_lock.py'))['acquire'](OUT)
    try:
        r = M['Run'](OUT); r.capture()
        for name, value in [('source-orders', list(r.source.values())), ('target-orders', list(r.target.values())), ('source-lines', list(r.sl.values())), ('target-lines', list(r.tl.values())), ('classification', r.rows)]: save(DEST / (name + '.json'), value)
        print('order capture complete', flush=True)
        extra_order = 'name state company_id partner_id partner_invoice_id partner_shipping_id date_order order_line client_order_ref origin quote_ref pricelist_id payment_term_id user_id warehouse_id note attn is_quotation_template woo_order_id'.split()
        extra_line = 'order_id sequence display_type name product_id product_uom product_uom_id product_uom_qty price_unit discount tax_id tax_ids route_id route_ids warehouse_id purchase_price packing_ratio base_price is_free is_expense'.split()
        for label, reader, orders, lines in [('source', r.a, r.source, r.sl), ('target', r.b, r.target, r.tl)]:
            save(DEST / (label + '-order-extra.json'), reader.read('sale.order', orders, extra_order))
            save(DEST / (label + '-line-extra.json'), reader.read('sale.order.line', lines, extra_line))
            partners = reader.read('res.partner', [rid(x.get(f)) for x in orders.values() for f in ['partner_id', 'partner_invoice_id', 'partner_shipping_id']], 'name parent_id commercial_partner_id type active company_type is_company vat email phone street street2 city zip country_id state_id property_stock_customer x_over_credit_limit x_need_followup_action x_studio_review_by_manager_studio'.split())
            parent_ids = {rid(x.get(f)) for x in partners for f in ['parent_id','commercial_partner_id']} - {x['id'] for x in partners} - {False}
            partners += reader.read('res.partner', parent_ids, list(partners[0]))
            save(DEST / (label + '-partners.json'), partners)
            save(DEST / (label + '-partner-xids.json'), reader.scan('ir.model.data', [['model', '=', 'res.partner'], ['res_id', 'in', [x['id'] for x in partners]]], ['module', 'name', 'model', 'res_id']))
            save(DEST / (label + '-warehouses.json'), reader.scan('stock.warehouse', [['company_id','=',1]], 'name code company_id lot_stock_id wh_input_stock_loc_id wh_output_stock_loc_id delivery_route_id route_ids delivery_steps out_type_id'.split()))
            routemodel = 'stock.location.route' if label == 'source' else 'stock.route'
            routes = reader.scan(routemodel, [], ['name','active','company_id','rule_ids','warehouse_ids'])
            save(DEST / (label + '-routes.json'), routes)
            save(DEST / (label + '-rules.json'), reader.read('stock.rule', [i for x in routes for i in x['rule_ids']], 'name active action procure_method route_id warehouse_id company_id location_src_id location_dest_id picking_type_id'.split()))
            print(label + ' partner and route evidence complete', flush=True)
        save(DEST / 'approval-rules.json', r.b.scan('studio.approval.rule', [['model_name','=','sale.order'],['method','=','action_confirm']], ['name','active','domain','can_validate','message','approver_ids','approval_group_id','exclusive_user','notification_order']))
        save(DEST / 'approval-entries.json', r.b.scan('studio.approval.entry', [['model','=','sale.order'],['res_id','in',list(r.target)]], ['rule_id','res_id','approved','user_id']))
        missing = [x for x in r.rows if x['classification']=='missing_target_order']
        names = [x['source_name'] for x in missing]
        candidates = r.b.scan('sale.order', ['|','|',['name','in',names],['client_order_ref','in',names],['origin','in',names]], extra_order)
        save(DEST / 'missing-order-candidates.json', candidates)
        save(DEST / 'missing-order-xids.json', r.b.scan('ir.model.data', [['model','=','sale.order'], ['name','in',['sale_order_'+str(x['source_id']) for x in missing]]], ['module','name','res_id']))
        for label, reader, ids in [('source',r.a,[43967,46485]),('target',r.b,[116777,130303,114459])]:
            products = reader.read('product.product',ids,'name display_name product_tmpl_id active barcode default_code uom_id tracking company_id type'.split())
            save(DEST / (label+'-suspect-products.json'),products)
            save(DEST / (label+'-suspect-product-xids.json'),reader.scan('ir.model.data',['|','&',['model','=','product.product'],['res_id','in',ids],'&',['model','=','product.template'],['res_id','in',[rid(x['product_tmpl_id']) for x in products]]],['module','name','model','res_id']))
        save(DEST / 'source-unit-1087.json',r.a.read('uom.uom',[1087],['name','factor','rounding','category_id','uom_type','active']))
        save(DEST / 'target-unit-470.json',r.b.read('uom.uom',[470],['name','factor','relative_factor','relative_uom_id','rounding','active']))
        save(DEST / 'complete.json',dict(captured_utc=M['now'](),read_only=True,identity=r.identity))
        print('SO remediation read-only capture complete',flush=True)
    finally: lock.close()


if __name__ == '__main__': main()
