"""Bruce-approved release of conflicting automatic holds from migrated SOs only."""
from collections import defaultdict
import json
from pathlib import Path

def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False

def release(r, needed, own_move_ids):
    out=r.reservation_evidence_dir
    approval=json.loads((out/'phases/operator-reservation-release-approval.json').read_text(encoding='utf8'))
    if not approval.get('approved') or approval.get('company_id')!=1 or approval.get('target_database')!='py19-main-33843450':raise RuntimeError('Scoped reservation approval missing')
    totals=defaultdict(lambda:[0.,0.])
    domain=[['company_id','=',1],['product_id','in',sorted({k[0] for k in needed})],['location_id','in',sorted({k[1] for k in needed})],['lot_id','in',sorted({k[2] for k in needed})],['package_id','=',False],['owner_id','=',False]]
    fields=['product_id','location_id','lot_id','quantity','reserved_quantity','package_id','owner_id']
    before=r.b.scan('stock.quant',domain,fields)
    for q in before:
        key=tuple(rid(q[f]) for f in ['product_id','location_id','lot_id']);totals[key][0]+=q['quantity'];totals[key][1]+=q['reserved_quantity']
    conflicts={key for key,(quantity,reserved) in totals.items() if key in needed and reserved>quantity+1e-6}
    if not conflicts:return
    if any(totals[key][0]+1e-6<needed[key] for key in needed):raise RuntimeError('Physical stock shortage; reservations cannot supply stock')
    lines=r.b.scan('stock.move.line',domain+[['state','not in',['done','cancel']],['quantity','>',0]],['move_id','picking_id','company_id','product_id','location_id','lot_id','quantity','picked','state'])
    other=[x for x in lines if tuple(rid(x[f]) for f in ['product_id','location_id','lot_id']) in conflicts and rid(x['move_id']) not in own_move_ids]
    if not other or any(x['picked'] or not x['picking_id'] for x in other):raise RuntimeError('Conflicting reservation is not an untouched native SO allocation')
    pids={rid(x['picking_id']) for x in other}
    picks=r.b.read('stock.picking',pids,['company_id','state','sale_id','move_ids','date_done'])
    confirmations=json.loads((out/'phases/so-confirmation-journal.json').read_text(encoding='utf8'))['orders']
    owners={x['target_id']:x for x in confirmations.values() if x['status']=='verified_confirmed' and not x.get('before',{}).get('picking_ids')}
    excluded=[p for p in picks if not owners.get(rid(p['sale_id'])) or p['id'] not in owners[rid(p['sale_id'])]['picking_ids']]
    picks=[p for p in picks if p not in excluded]
    if not picks:raise RuntimeError('Reservation belongs outside new scoped SO confirmations')
    pids={p['id'] for p in picks}
    other=[x for x in other if rid(x['picking_id']) in pids]
    for p in picks:
        entry=owners.get(rid(p['sale_id']))
        if not entry or p['id'] not in entry['picking_ids'] or rid(p['company_id'])!=1 or p['state'] in ['done','cancel'] or p['date_done']:raise RuntimeError('Reservation belongs outside new scoped SO confirmations')
        if set(p['move_ids'])!={x['id'] for x in entry['moves'] if rid(x['picking_id'])==p['id']}:raise RuntimeError('Scoped native picking moves changed')
    moves=r.b.read('stock.move',{i for p in picks for i in p['move_ids']},['company_id','state','picked','move_line_ids','purchase_line_id','production_id','raw_material_production_id','product_id'])
    if any(rid(x['company_id'])!=1 or x['state'] in ['done','cancel'] or x['picked'] or x['purchase_line_id'] or x['production_id'] or x['raw_material_production_id'] for x in moves):raise RuntimeError('Scoped native allocation already used or has another workflow')
    all_lines=r.b.read('stock.move.line',{i for x in moves for i in x['move_line_ids']},['picked','state'])
    if any(x['picked'] or x['state'] in ['done','cancel'] for x in all_lines):raise RuntimeError('Scoped allocation details already used')
    products={rid(x['product_id']) for x in moves}
    def physical():
        rows=r.b.scan('stock.quant',[['company_id','=',1],['product_id','in',sorted(products)]],fields)
        values=defaultdict(float)
        for x in rows:values[tuple(rid(x[f]) for f in ['product_id','location_id','lot_id','package_id','owner_id'])]+=x['quantity']
        return {str(k):v for k,v in values.items() if abs(v)>1e-8}
    proof=dict(picking_ids=sorted(pids),excluded_non_scoped_pickings=excluded,source='scoped SO confirmation journal; automatically allocated, entirely unpicked',conflicting_quants_before=before,conflicting_lines=other,pickings=picks,moves=moves,physical_before=physical(),status='intent')
    r.j.setdefault('scoped_reservation_releases',[]).append(proof);r.persist()
    r.mutate('stock.picking','do_unreserve',[sorted(pids)],jsonrpc=True)
    check=r.b.read('stock.move',[x['id'] for x in moves],['quantity','move_line_ids'])
    after_physical=physical()
    if any(abs(x['quantity'])>1e-8 or x['move_line_ids'] for x in check) or after_physical!=proof['physical_before']:raise RuntimeError('Scoped unreserve postcondition failed; readback required')
    proof.update(status='verified_released',physical_after=after_physical,readback=check);r.persist()
