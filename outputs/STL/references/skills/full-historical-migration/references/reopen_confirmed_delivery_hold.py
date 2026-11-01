"""Reopen only an old native approval hold now proven confirmed by the SO phase."""
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def reopen(r,g,confirmations):
    sid=g['source']['id'];tid=g['target']['id'];entry=r.j['groups'].get(str(sid),{})
    proof=confirmations.get(str(sid),{})
    if entry.get('phase')!='confirmation_held' or not entry.get('execution_hold') or entry.get('move_pairs') or entry.get('picking_pairs') or r.uncertain:raise RuntimeError('Not an untouched native confirmation hold')
    if proof.get('status')!='verified_confirmed' or proof.get('target_id')!=tid or g['issues']:raise RuntimeError('Scoped confirmation proof or current eligibility missing')
    if r.a.read('sale.order',[sid],list(g['source']))[0]!=g['source']:raise RuntimeError('Source SO changed')
    fresh=r.b.read('sale.order',[tid],list(g['target']))[0]
    if fresh!=g['target'] or fresh['state'] not in ['sale','done'] or rid(fresh['company_id'])!=1:raise RuntimeError('Live target differs from verified commercial snapshot')
    for model,reader,rows in [('sale.order.line',r.a,g['source_lines']),('sale.order.line',r.b,g['target_lines'])]:
        actual=reader.read(model,[x['id'] for x in rows],list(rows[0]));expected={x['id']:x for x in rows}
        if any(x!=expected[x['id']] for x in actual):raise RuntimeError('Source/target commercial lines changed')
    native=r.target_chain(tid)
    if not native or any(rid(x['company_id'])!=1 or x['state'] in ['done','cancel'] for x in native):raise RuntimeError('Native chain already used or missing')
    linechecks=r.b.read('stock.move.line',[i for x in native for i in x['move_line_ids']],['picked','state'])
    if any(x['picked'] or x['state']=='done' for x in linechecks):raise RuntimeError('Native operations already used')
    pids={rid(x['picking_id']) for x in native}
    if any(x['model']=='stock.picking' and x['method']=='button_validate' and set(x['args'][0])&pids for x in r.j['operations']):raise RuntimeError('Prior validation cannot be retried')
    domain=[['company_id','=',1],['move_type','in',['out_invoice','in_invoice','out_refund','in_refund']]]
    entry.setdefault('hold_history',[]).append(dict(reason=entry.get('hold_reason'),previous_invoice_baseline=entry.get('invoice_count_before'),released_by='live scoped SO confirmation readback',native_moves=native,confirmation=proof))
    entry.update(phase='order_confirmed',execution_hold=False,invoice_count_before=r.b.call('account.move','search_count',[domain]),confirmation_reused=True)
    r.persist();r.resume_unvalidated=True
