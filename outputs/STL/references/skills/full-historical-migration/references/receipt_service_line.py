"""A service commercial line is not a missing physical receipt."""
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def nonphysical_service(source_line,target_line,source_product,target_product,source_moves):
    return bool(target_line and source_product and target_product and source_product.get('type')=='service' and target_product.get('type')=='service' and abs(source_line['qty_received'])<1e-8 and not any(rid(m.get('purchase_line_id'))==source_line['id'] for m in source_moves))
