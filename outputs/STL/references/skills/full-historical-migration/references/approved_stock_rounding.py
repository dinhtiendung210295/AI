"""Exact per-UoM approved rounding evidence, never a shared numeric tolerance."""
from decimal import Decimal,ROUND_HALF_UP
def rid(x):return x[0] if isinstance(x,(tuple,list)) and x else x or False

def adjusted_source(move,lines,records,maps,source_units,target_units):
    adjusted=[];differences=[]
    for row in lines:
        record=records.get(row['id']);copy=dict(row)
        if record:
            unit=maps['uom.uom'].get(rid(row['product_uom_id']));precision=Decimal(str(target_units[unit]['rounding']))
            want=float((Decimal(str(row['qty_done']))/precision).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*precision)
            original=record.get('source_qty',record.get('source_quantity'));actual=record.get('target_qty',record.get('target_quantity'))
            if record['target_unit']!=unit or original!=row['qty_done'] or abs(actual-want)>1e-9:raise ValueError('Rounding journal does not match source/UoM policy')
            copy['qty_done']=want;differences.append(record)
        adjusted.append(copy)
    result=dict(move)
    if differences:
        factor=source_units[rid(move['product_uom'])]['factor']
        result['quantity_done']=sum(x['qty_done']*factor/source_units[rid(x['product_uom_id'])]['factor'] for x in adjusted)
    return result,adjusted,differences
