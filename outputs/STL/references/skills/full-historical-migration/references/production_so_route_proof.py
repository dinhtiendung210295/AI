"""Read-only pull-chain proof for existing warehouse/consignment SO routes."""
def rid(v):return v[0] if isinstance(v,(list,tuple)) and v else v or False

def inspect(reader):
    warehouses=reader.scan('stock.warehouse',[['company_id','=',1]],['name','code','company_id','lot_stock_id','route_ids','delivery_route_id','delivery_steps'])
    rules=reader.scan('stock.rule',[['active','=',True]],['name','active','action','procure_method','route_id','warehouse_id','company_id','location_src_id','location_dest_id','picking_type_id'])
    return dict(ready=True,warehouses={x['id']:x for x in warehouses},rules=rules)

def evaluate(order,lines,products,partners,categories,units,packages,proof,source_route_map):
    errors=[];chains=[];wid=rid(order.get('warehouse_id'));warehouse=proof['warehouses'].get(wid)
    if not warehouse:return ['warehouse_missing'],chains
    if rid(partners.get(rid(order.get('partner_shipping_id')),{}).get('property_stock_customer'))!=2:return ['shipping_location_unproven'],chains
    for line in lines:
        if line.get('display_type'):continue
        product=products.get(rid(line.get('product_id')), {})
        if product.get('type')=='service':continue
        explicit=set(line.get('route_ids',[]))
        if line.get('is_expense'):errors.append('expense_requires_review');continue
        if explicit=={126} and order.get('id') in proof.get('skip_procurement_order_ids',[]):
            if source_route_map.get(line['id'])!=17:errors.append('dropship_source_route_unproven')
            chains.append(dict(line_id=line['id'],existing_dropship_PO_dependency=True,stock_preparation_deferred=True))
            continue
        known={83:25,82:22}
        if explicit and not explicit<=set(known):errors.append('explicit_route_can_create_purchase_order_or_unproven_route');continue
        if explicit and any(source_route_map.get(line['id'])!=known[i] for i in explicit):errors.append('explicit_route_source_identity_unproven');continue
        if not explicit and rid(line.get('warehouse_id'))!=wid:errors.append('line_warehouse_mismatch');continue
        proutes=set(product.get('route_ids',[]))|set(categories.get(rid(product.get('categ_id')),{}).get('total_route_ids',[]))
        if not proutes<={4,5}:errors.append('product_route_unproven');continue
        package=packages.get(rid(units.get(rid(line.get('product_uom_id')),{}).get('package_type_id')), {})
        if not set(package.get('route_ids',[]))<=set(warehouse['route_ids'])|{3,4,5}:errors.append('packaging_route_unproven');continue
        allowed=explicit or (set(warehouse['route_ids'])|proutes)
        current=2;seen=set();chain=[]
        while True:
            if current in seen:errors.append('route_cycle');break
            seen.add(current)
            hits=[r for r in proof['rules'] if r['active'] and r['action']!='push' and rid(r['company_id']) in [False,1] and rid(r['warehouse_id']) in [False,wid] and rid(r['location_dest_id'])==current and rid(r['route_id']) in allowed]
            if len(hits)!=1:errors.append('pull_rule_not_unique');break
            rule=hits[0];chain.append(rule)
            if rule['action'] not in ['pull','pull_push']:errors.append('route_would_create_PO_or_MO');break
            if rule['procure_method']=='make_to_stock':
                if rid(rule['location_src_id'])!=rid(warehouse['lot_stock_id']):errors.append('stock_source_not_warehouse_stock')
                break
            if rule['procure_method']!='make_to_order':errors.append('unproven_procurement_method');break
            current=rid(rule['location_src_id'])
        chains.append(dict(line_id=line['id'],warehouse_id=wid,rules=chain))
    return sorted(set(errors)),chains
