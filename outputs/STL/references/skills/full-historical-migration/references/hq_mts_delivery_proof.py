"""Read-only proof of the HQ customer pull rule; no route/master overrides."""
def rid(value):return value[0] if isinstance(value,(list,tuple)) and value else value or False


def evaluate(warehouse, locations, rules, picking):
    errors=[]
    if warehouse['id']!=1 or rid(warehouse['company_id'])!=1 or rid(warehouse['lot_stock_id'])!=5 or rid(warehouse['delivery_route_id'])!=3 or warehouse['delivery_steps']!='pick_pack_ship':errors.append('warehouse_configuration')
    allowed=set(warehouse['route_ids'])|{4,5}
    ancestors={x['id'] for x in locations}
    matches=[x for x in rules if x['active'] and x['action']!='push' and rid(x['route_id']) in allowed and rid(x['location_dest_id']) in ancestors and rid(x['warehouse_id']) in [False,1] and rid(x['company_id']) in [False,1]]
    if len(matches)!=1 or matches[0]['id']!=9 or matches[0]['action']!='pull' or matches[0]['procure_method']!='make_to_stock' or rid(matches[0]['location_src_id'])!=5 or rid(matches[0]['location_dest_id'])!=2:errors.append('customer_pull_not_uniquely_verified_mts')
    if not locations or locations[0]['id']!=2 or locations[0]['usage']!='customer' or 5 in ancestors:errors.append('customer_location_hierarchy')
    if rid(picking['warehouse_id'])!=1 or rid(picking['default_location_src_id'])!=5 or rid(picking['default_location_dest_id'])!=9:errors.append('pick_operation_configuration')
    return {'ready':not errors,'errors':errors,'warehouse':warehouse,'customer_locations':locations,'applicable_customer_rules':matches,'picking':picking,'allowed_product_routes':[4,5]}


def inspect(reader):
    warehouse=reader.read('stock.warehouse',[1],['company_id','lot_stock_id','delivery_route_id','delivery_steps','route_ids'])[0]
    locations=[];current=2
    while current:
        if current in {x['id'] for x in locations}:raise RuntimeError('Location parent cycle')
        location=reader.read('stock.location',[current],['location_id','usage'])[0];locations.append(location);current=rid(location['location_id'])
    rules=reader.scan('stock.rule',[['route_id','in',list(set(warehouse['route_ids'])|{4,5})]],['active','action','procure_method','location_src_id','location_dest_id','route_id','warehouse_id','company_id','picking_type_id'])
    root=next((x for x in rules if x['id']==9),None)
    if not root:return {'ready':False,'errors':['missing_rule_9']}
    picking=reader.read('stock.picking.type',[rid(root['picking_type_id'])],['warehouse_id','default_location_src_id','default_location_dest_id'])[0]
    return evaluate(warehouse,locations,rules,picking)


def live_order_gate(reader, order, lines):
    proof=inspect(reader)
    if not proof['ready']:return proof
    errors=[]
    if rid(order['warehouse_id'])!=1:errors.append('order_not_hq')
    partner=reader.read('res.partner',[rid(order['partner_shipping_id'])],['property_stock_customer'])[0]
    if rid(partner['property_stock_customer'])!=2:errors.append('customer_property_not_verified_location')
    live_lines=reader.read('sale.order.line',[x['id'] for x in lines],['warehouse_id','route_ids','is_expense','product_id','product_uom_id'])
    if any(x['route_ids'] or x['is_expense'] or (x['product_id'] and rid(x['warehouse_id'])!=1) for x in live_lines):errors.append('line_procurement_override')
    products=reader.read('product.product',[rid(x['product_id']) for x in live_lines if x['product_id']],['type','route_ids','categ_id'])
    categories={x['id']:x for x in reader.read('product.category',[rid(x['categ_id']) for x in products],['total_route_ids'])}
    for product in products:
        if product['type']=='service':continue
        routes=set(product['route_ids'])|set(categories[rid(product['categ_id'])]['total_route_ids'])
        if not routes<={4,5}:errors.append('product_or_category_route_outside_proof')
    units=reader.read('uom.uom',[rid(x['product_uom_id']) for x in live_lines if x['product_uom_id']],['package_type_id'])
    packages=reader.read('stock.package.type',[rid(x['package_type_id']) for x in units if x['package_type_id']],['route_ids'])
    if any(not set(x['route_ids'])<={3,4,5} for x in packages):errors.append('packaging_route_outside_proof')
    proof.update(ready=not errors,errors=errors,shipping_partner=partner,lines=live_lines,products=products,categories=list(categories.values()),unit_packaging=units,packages=packages)
    return proof
