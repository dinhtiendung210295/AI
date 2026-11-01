"""Identify physical stage quantities differing from the final customer leg."""
from collections import defaultdict
from decimal import Decimal
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def differs(moves,locations,maps,units):
    stages=defaultdict(Decimal);customer=defaultdict(Decimal)
    for move in moves:
        product=rid(move['product_id']);src=rid(move['location_id']);dst=rid(move['location_dest_id']);unit=maps['uom.uom'][rid(move['product_uom'])]
        quantity=Decimal(str(move['product_uom_qty']))*Decimal(str(units[unit]['factor']))
        if locations[dst]['usage']=='customer':customer[product]+=quantity
        elif locations[src]['usage']=='internal' and locations[dst]['usage']=='internal':stages[(product,src,dst)]+=quantity
    return any(product in customer and abs(quantity-customer[product])>Decimal('0.000001') for (product,src,dst),quantity in stages.items())
