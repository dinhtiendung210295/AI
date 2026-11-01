"""Deletion allowed only for this job's duplicate, unconsumed/unlinked preparation."""
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def check(extra,original,source,operation,product,unit,line,company,actor):
    if operation.get('model')!='stock.move' or operation.get('method')!='create' or operation.get('status')!='returned' or operation.get('result')!=extra['id']:raise ValueError('Not a returned creation by this job')
    values=operation['args'][0]
    for field,want in [('product_id',product),('product_uom',unit),('sale_line_id',line),('company_id',company),('location_id',rid(original['location_id'])),('location_dest_id',rid(original['location_dest_id'])),('picking_id',rid(original['picking_id']))]:
        if rid(extra.get(field))!=want or rid(values.get(field))!=want:raise ValueError('Duplicate preparation identity changed')
    for row in [extra,original]:
        if any(rid(row.get(field))!=want for field,want in [('product_id',product),('product_uom',unit),('sale_line_id',line),('company_id',company)]):raise ValueError('Not the same commercial/physical identity')
        if row['state'] in ['done','cancel'] or abs(row['quantity'])>1e-8 or row['picked'] or row['move_line_ids'] or row['move_orig_ids'] or row['move_dest_ids'] or rid(row['company_id'])!=company:raise ValueError('Stock already used or linked')
        if any(row.get(field) for field in ['origin_returned_move_id','returned_move_ids','production_id','raw_material_production_id','created_production_id','purchase_line_id','bom_line_id']):raise ValueError('Other business dependency')
    if rid(extra['create_uid'])!=actor or extra.get('rule_id') or extra.get('origin'):raise ValueError('Not this job standalone creation')
    desired=source['product_uom_qty']
    if abs(source['quantity_done']-desired)>1e-6 or values['product_uom_qty']!=desired or extra['product_uom_qty']!=desired or original['product_uom_qty']==desired:raise ValueError('Not a duplicate caused by physical demand mismatch')
    return True
