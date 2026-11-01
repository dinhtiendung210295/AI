"""Resume staged stock only after fresh ownership/detail proof; never retry validation."""
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False

def check_attempts(operations,picking_ids,completed):
    pending=set(picking_ids)-set(completed)
    if any(x['model']=='stock.picking' and x['method']=='button_validate' and set(x['args'][0])&pending for x in operations):raise RuntimeError('Earlier validation attempt requires separate readback; do not retry')

def verify(r,g):
    state=r.j['groups'][str(g['source']['id'])]
    if state['phase']!='chain_prepared' or r.uncertain:raise RuntimeError('Only an unambiguous prepared chain may resume')
    pairs={int(s):t for s,t in state['move_pairs'].items()};picks={int(s):t for s,t in state['picking_pairs'].items()}
    completed={picks[x] for x in state.get('completed_pickings',[])}
    check_attempts(r.j['operations'],set(picks.values()),completed)
    source=r.a.read('sale.order',[g['source']['id']],list(g['source']))[0]
    if source!=g['source']:raise RuntimeError('Source SO changed before prepared-chain continuation')
    fields=['state','date','quantity_done','product_id','product_uom','location_id','location_dest_id','move_line_ids','write_date','move_orig_ids','move_dest_ids']
    fresh=r.a.read('stock.move',g['moves'],fields)
    for row in fresh:
        for field in fields:
            want=r.sm[row['id']][field];have=row[field]
            if (set(want)!=set(have)) if field.endswith('_ids') else (want!=have):raise RuntimeError('Source move changed before prepared-chain continuation')
    source_lines={x['id']:x for mid in g['moves'] for x in r.by_move[mid]}
    details=r.a.read('stock.move.line',source_lines,list(next(iter(source_lines.values()))))
    if any(x!=source_lines[x['id']] for x in details):raise RuntimeError('Source execution details changed')
    target=r.b.read('stock.picking',set(picks.values()),['state','company_id','move_ids'])
    if any(rid(x['company_id'])!=1 or x['state']=='cancel' or ((x['state']=='done')!=(x['id'] in completed)) for x in target):raise RuntimeError('Prepared picking state differs from journal; no validation retry')
    if {mid for x in target for mid in x['move_ids']}!=set(pairs.values()) or {x['id'] for x in r.target_chain(g['target']['id'])}!=set(pairs.values()):raise RuntimeError('Prepared chain has unexpected moves')
    linefields=['move_id','product_id','product_uom_id','quantity','lot_id','location_id','location_dest_id','owner_id','package_id','result_package_id','date','picked','state']
    actual=r.b.scan('stock.move.line',[['move_id','in',list(pairs.values())]],linefields)
    mapped={r.maps.get('stock.move.line',{}).get(sid):x for sid,x in source_lines.items() if r.maps.get('stock.move.line',{}).get(sid)}
    for line in actual:
        src=mapped.get(line['id'])
        if not src:
            if line['picked'] or line['state']=='done':raise RuntimeError('Unknown picked/done prepared operation')
            continue
        unit=r.maps['uom.uom'][rid(src['product_uom_id'])]
        wanted={'move_id':pairs[rid(src['move_id'])],'product_id':r.maps['product.product'][rid(src['product_id'])],'product_uom_id':unit,'lot_id':r.maps.get('stock.lot',{}).get(rid(src['lot_id']),False),'location_id':r.maps['stock.location'][rid(src['location_id'])],'location_dest_id':r.maps['stock.location'][rid(src['location_dest_id'])],'owner_id':False,'package_id':False,'result_package_id':False,'date':src['date'],'quantity':r.round_prepared_quantity(src['qty_done'],r.tu[unit]['rounding'])}
        for field,want in wanted.items():
            have=rid(line[field]) if field.endswith('_id') else line[field]
            if have!=want:raise RuntimeError('Prepared historical detail changed: '+field)
    if set(mapped)-{x['id'] for x in actual}:raise RuntimeError('Prepared mapped lines are missing')
    state.setdefault('continuation_readbacks',[]).append(dict(pickings=target,move_lines=actual,source_moves=fresh,prior_validation_repeated=False));r.persist()
