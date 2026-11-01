"""Match an actual historical count delta; never invent opening/temporary stock."""
def rid(value):return value[0] if isinstance(value,(list,tuple)) and value else value or False


def match_count(move, detail, header, lines, sign, internal_location):
    if header['state']!='done' or rid(header['company_id'])!=1 or move['id'] not in header['move_ids']:raise RuntimeError('source_inventory_not_done_or_wrong_parent')
    candidates=[x for x in lines if rid(x['inventory_id'])==header['id'] and rid(x['product_id'])==rid(move['product_id']) and rid(x['location_id'])==internal_location and rid(x['prod_lot_id'])==rid(detail['lot_id']) and not x['package_id'] and not x['partner_id']]
    if len(candidates)!=1:raise RuntimeError('source_count_line_not_unique')
    count=candidates[0]
    if rid(count['product_uom_id'])!=rid(move['product_uom']) or rid(detail['product_uom_id'])!=rid(move['product_uom']):raise RuntimeError('source_count_unit_differs')
    if abs((count['product_qty']-count['theoretical_qty'])-sign*move['quantity_done'])>1e-8 or abs(detail['qty_done']-move['quantity_done'])>1e-8:raise RuntimeError('source_count_delta_differs_from_done_move')
    return count
