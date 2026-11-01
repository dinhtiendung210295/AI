"""Exact operator-approved raw demand exceptions; never adjusts MO headers."""
from decimal import Decimal, ROUND_HALF_UP


def demand_quantity(mo, move, unit, rounding, approval):
    original = move['product_uom_qty']
    rows = [x for x in approval.get('approved_rows', []) if x['source_id'] == move['id']]
    if not rows:
        return original, None
    if len(rows) != 1:
        raise RuntimeError('Duplicate demand approval')
    x = rows[0]
    if (mo['id'] not in approval['approved_source_mos'] or x['source_mo'] != mo['id']
            or move['id'] not in mo['move_raw_ids'] or x['model'] != 'stock.move'
            or x['role'] != 'raw' or x['field'] != 'product_uom_qty'
            or x['source_quantity'] != original or x['target_unit'] != unit
            or x['precision'] != rounding):
        raise RuntimeError('Demand approval scope/source/unit drift')
    step = Decimal(str(rounding))
    value = float((Decimal(str(original)) / step).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * step)
    if value <= 0 or value != x['proposed_target_quantity']:
        raise RuntimeError('Invalid approved demand rounding')
    return value, dict(x, decision='operator_approved', target_quantity=value)
