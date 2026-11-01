"""Allow only isolated native unpicked reservations in an interrupted preparation."""
from collections import defaultdict
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False

def validate(moves,lines,mapped_lines):
    byid={x['id']:x for x in moves};expected={lid for x in moves for lid in x['move_line_ids']};totals=defaultdict(float)
    if {x['id'] for x in lines}!=expected or expected&set(mapped_lines):raise RuntimeError('Unexpected historical or missing reservation lines')
    for x in lines:
        mid=rid(x['move_id'])
        if mid not in byid or x['state'] in ['done','cancel'] or x['picked'] or rid(x['company_id'])!=1 or x['quantity']<0 or x['owner_id'] or x['package_id'] or x['result_package_id']:raise RuntimeError('Reservation is not unconsumed native detail')
        if any(rid(x[f])!=rid(byid[mid][f]) for f in ['product_id','location_id','location_dest_id']):raise RuntimeError('Reservation dimensions differ from native move')
        totals[mid]+=x['quantity']
    if any(x['state'] in ['done','cancel'] or x['picked'] or rid(x['company_id'])!=1 or abs(x['quantity']-totals[x['id']])>1e-8 for x in moves):raise RuntimeError('Native reservation totals or state differ')

def capture(r,lines):
    keys={(rid(x['product_id']),rid(x['location_id']),rid(x['lot_id'])) for x in lines}
    if not keys:return {}
    rows=r.b.scan('stock.quant',[['company_id','=',1],['product_id','in',sorted({k[0] for k in keys})],['location_id','in',sorted({k[1] for k in keys})],['lot_id','in',sorted({k[2] for k in keys})],['owner_id','=',False],['package_id','=',False]],['product_id','location_id','lot_id','quantity'])
    values={str(k):0.0 for k in keys}
    for x in rows:
        k=(rid(x['product_id']),rid(x['location_id']),rid(x['lot_id']))
        if k in keys:values[str(k)]+=x['quantity']
    return values

def unchanged(before,after):
    if set(before)!=set(after) or any(abs(before[k]-after[k])>1e-8 for k in before):raise RuntimeError('Physical stock changed during native reservation release')
