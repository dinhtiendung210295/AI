"""Bind interchangeable, own unpicked MO placeholders before historical details."""
def choose(candidates, expected_demand, mapped_target=None):
    if mapped_target is not None:
        candidates=[x for x in candidates if x['id']==mapped_target]
    candidates=[x for x in candidates if abs(x['product_uom_qty']-expected_demand)<=1e-8]
    if not candidates:raise RuntimeError('Missing native MO placeholder with exact demand')
    if any(x['state'] in ['done','cancel'] or x['picked'] or x['move_orig_ids'] or x['move_dest_ids'] or x['origin_returned_move_id'] for x in candidates):
        raise RuntimeError('Ambiguous MO moves are not interchangeable unpicked placeholders')
    if len(candidates)==1:return candidates[0],False
    return min(candidates,key=lambda x:x['id']),True
