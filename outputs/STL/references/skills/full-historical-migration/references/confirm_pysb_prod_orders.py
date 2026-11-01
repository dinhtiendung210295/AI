"""Production order confirmation adapter. PO only until SO workflow is tested.

Never validates receipts, changes masters, creates invoices or retries RPCs.
The controller owns the OS lock and frozen-scope authorization.
"""
import json
import copy
import os
import time
import uuid
import runpy
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
I = runpy.run_path(str(BASE / 'inspect_pysb_aug_oct_prod.py'))
R = runpy.run_path(str(BASE / 'inspect_pysb_phase_readiness.py'))
W = runpy.run_path(str(BASE / 'production_workflow_rpc.py'))
Log = runpy.run_path(str(BASE / 'production_operation_log.py'))['OperationLog']
rid = R['rid']
digest = R['digest']


def load(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def save(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.' + str(os.getpid()) + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('w', encoding='utf8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    # Windows readers can momentarily prevent rename; retry only the local
    # atomic replacement, never an ERP mutation.
    for attempt in range(30):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt==29:raise
            time.sleep(0.1)


def vendor_issues(order, lines, products, sellers, parent):
    issues = []
    vendor = {rid(order['partner_id']), rid(parent)} - {False}
    for line in lines:
        if line.get('display_type'):
            continue
        product = products.get(rid(line.get('product_id')))
        if not product:
            issues.append('product_metadata_missing:' + str(line['id']))
            continue
        seller_ids = product.get('seller_ids', [])
        if len(seller_ids) <= 10 and not vendor.intersection(rid(sellers[x]['partner_id']) for x in seller_ids):
            issues.append('confirmation_may_create_supplier_master:' + str(line['id']))
    return issues


def assert_fresh(expected, actual, label):
    if expected != actual:
        raise RuntimeError(label + ' changed since readback; replan required')


class ConfirmPO:
    def __init__(self, directory, identity, readiness, recovery=False):
        self.out = Path(directory)
        self.phase = self.out / 'phases'
        self.identity = identity
        self.readiness = readiness
        self.session_token = None
        self.a = I['ReadOnly']('v14-prod', ('http://175.145.85.151', 'paoyeang_live'))
        self.b = I['ReadOnly']('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450'))
        self.log = Log(self.phase, identity)
        if self.log.unresolved() and not recovery:
            raise RuntimeError('Unresolved phase mutation requires readback recovery')
        self.maps = {model: {int(k): v for k, v in pairs.items()} for model, pairs in load(self.out / 'resolved-master-evidence.json')['maps'].items()}
        self.maps, proof = runpy.run_path(str(BASE / 'approved_order_currency_mapping.py'))['apply'](self.maps, self.a.scan('res.currency', [['name', '=', 'CNH']], ['name', 'rounding']), self.b.scan('res.currency', [['name', '=', 'CNY']], ['name', 'rounding']))
        save(self.phase / 'order-currency-map-evidence.json', proof)
        self.j = load(self.phase / 'order-confirmation-journal.json') if (self.phase / 'order-confirmation-journal.json').exists() else dict(identity=identity, orders={})
        self.chains = load(self.phase / 'native-chain-index.json') if (self.phase / 'native-chain-index.json').exists() else dict(identity=identity, orders={})
        if self.j['identity'] != identity or self.chains['identity'] != identity:
            raise RuntimeError('Order journal identity mismatch')
        self.source = {x['id']: x for x in load(self.phase / 'source-purchase.order.json')}
        self.target = {x['id']: x for x in load(self.phase / 'target-purchase.order.json')}
        self.sl = {x['id']: x for x in load(self.phase / 'source-purchase.order.line.json')}
        self.tl = {x['id']: x for x in load(self.phase / 'target-purchase.order.line.json')}

    def persist(self):
        save(self.phase / 'order-confirmation-journal.json', self.j)
        save(self.phase / 'native-chain-index.json', self.chains)

    def never_attempted(self, sid):
        for event in self.log.events:
            payload = event['payload']
            if event['kind'] == 'intent' and (payload.get('source_id') == sid or sid in payload.get('source_ids', [])):
                return False
        return True

    def recheck_supplier_holds(self):
        saved = load(self.phase / 'po-held-supplier-evidence.json')
        if saved['identity'] != self.identity:
            raise RuntimeError('Supplier evidence belongs to another scope')
        history = self.phase / 'history'
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        save(history / ('order-journal-before-supplier-review-' + stamp + '.json'), self.j)
        reopened = []
        for sid in saved['safe_to_recheck_source_ids']:
            key = 'purchase.order:' + str(sid)
            prior = self.j['orders'][key]
            if prior['status'] != 'held_workflow' or not self.never_attempted(sid):
                raise RuntimeError('Only never-attempted supplier workflow holds can be reopened')
            row = next(r for r in self.readiness['models']['purchase.order']['rows'] if r['source_id'] == sid)
            current = self.preflight(row)
            if current['issues']:
                continue
            self.j['orders'][key] = dict(source_model='purchase.order', source_id=sid, target_id=row['target_id'], status='reopened_workflow_preflight', prior_workflow_hold=copy.deepcopy(prior), reviewed_utc=datetime.now(timezone.utc).isoformat(), evidence='po-held-supplier-evidence.json', native_attempt_count=0)
            reopened.append(sid)
        self.persist()
        return reopened

    def chain(self, target_id):
        order = self.b.read('purchase.order', [target_id], ['picking_ids', 'order_line'])[0]
        picks = self.b.read('stock.picking', order['picking_ids'], ['company_id', 'state', 'move_ids', 'date_done'])
        frontier = {i for p in picks for i in p['move_ids']}
        moves = {}
        fields = 'company_id state product_id product_uom product_uom_qty quantity picked purchase_line_id sale_line_id picking_id move_orig_ids move_dest_ids move_line_ids location_id location_dest_id'.split()
        while frontier:
            rows = self.b.read('stock.move', frontier, fields)
            moves.update({x['id']: x for x in rows})
            frontier = {i for x in rows for i in x['move_dest_ids']} - set(moves)
        lines = self.b.read('stock.move.line', [i for x in moves.values() for i in x['move_line_ids']], ['move_id', 'state', 'picked', 'quantity', 'lot_id', 'package_id', 'owner_id'])
        return dict(order_line_ids=order['order_line'], pickings=picks, moves=list(moves.values()), move_lines=lines)

    def counters(self):
        return {model: self.b.call(model, 'search_count', [[['company_id', '=', 1]]]) for model in ('account.move', 'mrp.production', 'purchase.order')}

    def verify_supplier_changes(self, preflight, products_after, entry):
        assert_fresh(preflight['products'], {x['id']: x for x in products_after}, 'Supplier master')

    def preflight(self, row):
        sid = row['source_id']
        tid = row['target_id']
        s = self.source[sid]
        t = self.target[tid]
        assert_fresh(s, self.a.read('purchase.order', [sid], list(s))[0], 'Source PO')
        assert_fresh(t, self.b.read('purchase.order', [tid], list(t))[0], 'Target PO')
        sl = [self.sl[i] for i in s['order_line']]
        tl = [self.tl[i] for i in t['order_line']]
        for reader, model, expected in ((self.a, 'purchase.order.line', sl), (self.b, 'purchase.order.line', tl)):
            current = {x['id']: x for x in reader.read(model, [x['id'] for x in expected], list(expected[0]) if expected else [])}
            assert_fresh({x['id']: x for x in expected}, current, model)
        product_ids = {rid(x['product_id']) for x in tl if x.get('product_id')}
        products = {x['id']: x for x in self.b.read('product.product', product_ids, ['seller_ids', 'active'])}
        sellers = {x['id']: x for x in self.b.read('product.supplierinfo', [i for p in products.values() for i in p['seller_ids']], ['partner_id'])}
        partner = self.b.read('res.partner', [rid(t['partner_id'])], ['parent_id', 'active'])[0]
        issues = vendor_issues(t, tl, products, sellers, partner['parent_id'])
        if not partner['active'] or any(not x['active'] for x in products.values()):
            issues.append('archived_vendor_or_product')
        if not s.get('date_approve'):
            issues.append('source_approval_date_missing')
        chain = self.chain(tid)
        if chain['pickings'] or chain['moves']:
            issues.append('draft_order_already_has_native_chain')
        return dict(source=s, target=t, source_lines=sl, target_lines=tl, products=products, suppliers=sellers, before_chain=chain, issues=issues)

    def mutate(self, sid, tid, method, args, before):
        oid = self.identity['scope_hash'] + ':purchase.order:' + str(sid) + ':' + method
        self.log.append_intent(dict(operation_id=oid, phase='confirm-po', source_model='purchase.order', source_id=sid, target_id=tid, method=method, args=args, before=before))
        try:
            result = W['call'](self.b.r, 'purchase.order', method, args, {'context': {'pysb_phase_token': self.session_token, 'tz': 'UTC', 'tracking_disable': True, 'mail_notrack': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True, 'mail_auto_subscribe_no_notify': True, 'send_email': False}})
        except Exception:
            # No exception payload: remote errors may echo sensitive context.
            self.log.mark_uncertain(oid, 'RPC failed; readback required before any further write')
            raise
        self.log.append_result(oid, {'returned': True, 'result': result})
        return oid

    def confirm(self, row, preflight):
        sid, tid = row['source_id'], row['target_id']
        key = 'purchase.order:' + str(sid)
        previous = self.j['orders'].get(key)
        if previous and previous.get('status') != 'reopened_workflow_preflight':
            if previous.get('status') == 'verified_confirmed':
                live = self.b.read('purchase.order', [tid], ['state', 'date_approve'])[0]
                if live['state'] != 'purchase' or live['date_approve'] != previous['historical_date']:
                    raise RuntimeError('Previously confirmed PO changed; inspect without reconfirming')
                return previous
            raise RuntimeError('Prepared prior order needs readback recovery; no repeated confirmation')
        if previous and not self.never_attempted(sid):
            raise RuntimeError('Reopened workflow hold has a prior mutation intent')
        if preflight['issues']:
            raise RuntimeError('Held PO cannot be confirmed')
        # Recheck headers, lines, suppliers immediately before the first write.
        fresh = self.preflight(row)
        assert_fresh(preflight, fresh, 'PO preflight')
        before_counts = self.counters()
        entry = dict(source_model='purchase.order', source_id=sid, target_id=tid, status='prepared', before_state=row['target_state'], historical_date=preflight['source']['date_approve'], before_chain=preflight['before_chain'], counters_before=before_counts)
        if previous:
            entry['prior_workflow_hold'] = previous
        self.j['orders'][key] = entry
        self.persist()
        entry['confirm_operation_id'] = self.mutate(sid, tid, 'button_confirm', [[tid]], preflight)
        return self.finish_confirmed(row, preflight, entry, before_counts)

    def confirm_recordset(self, selected):
        if not 1 < len(selected) <= 25:
            raise RuntimeError('Recordset pilot/batch requires 2..25 distinct PO')
        tids = [row['target_id'] for row, _ in selected]
        if len(tids) != len(set(tids)):
            raise RuntimeError('Duplicate target in confirmation recordset')
        for row, preflight in selected:
            previous = self.j['orders'].get('purchase.order:' + str(row['source_id']))
            if preflight['issues'] or (previous and (previous.get('status') != 'reopened_workflow_preflight' or not self.never_attempted(row['source_id']))):
                raise RuntimeError('Held or previously attempted order in recordset')
            assert_fresh(preflight, self.preflight(row), 'Recordset PO preflight')
        counters = self.counters()
        oid = self.identity['scope_hash'] + ':purchase.order:recordset:' + digest(tids)
        for row, preflight in selected:
            key = 'purchase.order:' + str(row['source_id'])
            previous = self.j['orders'].get(key)
            self.j['orders'][key] = dict(source_model='purchase.order', source_id=row['source_id'], target_id=row['target_id'], status='prepared_recordset', before_state=row['target_state'], historical_date=preflight['source']['date_approve'], before_chain=preflight['before_chain'], counters_before=counters, confirm_operation_id=oid)
            if previous:
                self.j['orders'][key]['prior_workflow_hold'] = previous
        self.persist()
        self.log.append_intent(dict(operation_id=oid, phase='confirm-po', source_model='purchase.order', source_ids=[r['source_id'] for r, _ in selected], target_ids=tids, method='button_confirm', args=[tids], before=[p for _, p in selected], counters_before=counters))
        try:
            value = W['call'](self.b.r, 'purchase.order', 'button_confirm', [tids], {'context': {'pysb_phase_token': self.session_token, 'tz': 'UTC', 'tracking_disable': True, 'mail_notrack': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True, 'mail_auto_subscribe_no_notify': True, 'send_email': False}})
        except Exception:
            self.log.mark_uncertain(oid, 'Recordset RPC failed; read every PO before any retry')
            readback = self.b.read('purchase.order', tids, ['state', 'date_approve', 'picking_ids'])
            save(self.phase / ('recordset-uncertain-' + digest(tids) + '.json'), dict(operation_id=oid, rows=readback, retry_authorized=False))
            raise
        self.log.append_result(oid, dict(returned=True, result=value))
        # Native approval may accept only a subset: always classify per order.
        live = {x['id']: x for x in self.b.read('purchase.order', tids, ['state', 'date_approve', 'picking_ids'])}
        completed = []
        held = []
        for row, preflight in selected:
            entry = self.j['orders']['purchase.order:' + str(row['source_id'])]
            entry['after_state'] = live[row['target_id']]['state']
            if entry['after_state'] != 'purchase':
                entry.update(status='held_native_approval', reasons=['Native recordset confirmation did not reach purchase'], after_chain=self.chain(row['target_id']))
                held.append(entry)
                self.persist()
                continue
            completed.append(self.finish_confirmed(row, preflight, entry, counters))
        if self.counters() != counters:
            raise RuntimeError('Recordset changed invoice/MO/PO counts')
        return dict(completed=completed, held=held, native_confirm_rpc_calls=1, target_ids=tids)

    def finish_confirmed(self, row, preflight, entry, before_counts):
        sid, tid = row['source_id'], row['target_id']
        key = 'purchase.order:' + str(sid)
        current = self.b.read('purchase.order', [tid], ['state', 'date_approve'])[0]
        after_chain = self.chain(tid)
        entry.update(after_state=current['state'], native_chain_ids=dict(picking_ids=[x['id'] for x in after_chain['pickings']], move_ids=[x['id'] for x in after_chain['moves']]), after_chain=after_chain)
        self.persist()
        if current['state'] != 'purchase':
            entry['status'] = 'held_native_approval'
            self.persist()
            raise RuntimeError('Native confirmation did not reach purchase; inspect approval, no retry')
        validate_new_chain(after_chain, preflight['target']['order_line'])
        if self.counters() != before_counts:
            raise RuntimeError('Unexpected invoice/MO/PO count change; stop for readback')
        products_after = self.b.read('product.product', list(preflight['products']), ['seller_ids', 'active'])
        self.verify_supplier_changes(preflight, products_after, entry)
        entry['date_operation_id'] = self.mutate(sid, tid, 'write', [[tid], {'date_approve': entry['historical_date']}], current)
        verified = self.b.read('purchase.order', [tid], ['state', 'date_approve'])[0]
        if verified['state'] != 'purchase' or verified['date_approve'] != entry['historical_date']:
            raise RuntimeError('Historical approval date readback failed')
        # Commercial fields and all lines must survive native confirmation.
        final_header = self.b.read('purchase.order', [tid], list(preflight['target']))[0]
        expected_header = dict(preflight['target'])
        for field in ('state', 'date_approve', 'picking_ids', 'write_date'):
            expected_header[field] = final_header.get(field)
        assert_fresh(expected_header, final_header, 'PO commercial header after confirmation')
        expected_lines = {x['id']: x for x in preflight['target_lines']}
        actual_lines = {x['id']: x for x in self.b.read('purchase.order.line', list(expected_lines), list(next(iter(expected_lines.values()))) if expected_lines else [])}
        for lid in expected_lines:
            expected_lines[lid] = dict(expected_lines[lid], write_date=actual_lines[lid].get('write_date'))
        assert_fresh(expected_lines, actual_lines, 'PO commercial lines after confirmation')
        if self.counters() != before_counts:
            raise RuntimeError('Counters changed during historical date restoration')
        entry.update(status='verified_confirmed', confirmed=True, after_state='purchase', warehouse_done_by_this_phase=0, new_invoices=0, completed_utc=datetime.now(timezone.utc).isoformat())
        self.chains['orders'][key] = dict(source_model='purchase.order', source_id=sid, target_id=tid, provenance='created_by_phase', operation_id=entry['confirm_operation_id'], before_hash=digest(preflight['before_chain']), after_hash=digest(after_chain), before=preflight['before_chain'], after=after_chain, line_mappings={str(x['id']): self.maps.get('purchase.order.line', {}).get(x['id']) for x in preflight['source_lines']}, preparation_authorized=False, note='Stock adapter must revalidate live chain and scope before preparation; reservation cleanup not authorized by this index alone.')
        self.persist()
        self.log.build_checkpoint()
        return entry

    def inspect_recovery(self, sid):
        key = 'purchase.order:' + str(sid)
        entry = self.j['orders'][key]
        oid = self.identity['scope_hash'] + ':purchase.order:' + str(sid) + ':button_confirm'
        unresolved = self.log.unresolved()
        if set(unresolved) != {oid} or entry['status'] != 'prepared':
            raise RuntimeError('Recovery limited to the single recorded confirmation intent')
        intent = next(x for x in self.log.events if x['operation_id'] == oid and x['kind'] == 'intent')
        preflight = copy.deepcopy(intent['payload']['before'])
        # JSON keys normalize to strings on disk; restore local indexing only.
        preflight['products'] = {int(k): v for k, v in preflight['products'].items()}
        tid = entry['target_id']
        source = self.a.read('purchase.order', [sid], list(preflight['source']))[0]
        assert_fresh(preflight['source'], source, 'Recovery source header')
        for reader, model, expected in ((self.a, 'purchase.order.line', preflight['source_lines']), (self.b, 'purchase.order.line', preflight['target_lines'])):
            current = {x['id']: x for x in reader.read(model, [x['id'] for x in expected], list(expected[0]) if expected else [])}
            for item in expected:
                if model == 'purchase.order.line' and 'write_date' in item:
                    item = dict(item, write_date=current[item['id']]['write_date'])
                assert_fresh(item, current[item['id']], 'Recovery ' + model)
        live = self.b.read('purchase.order', [tid], list(preflight['target']))[0]
        if live['state'] != 'purchase':
            raise RuntimeError('Readback does not prove PO confirmed; no retry authorized')
        expected = dict(preflight['target'])
        for field in ('state', 'date_approve', 'picking_ids', 'write_date'):
            expected[field] = live.get(field)
        assert_fresh(expected, live, 'Recovery target commercial header')
        products = self.b.read('product.product', list(preflight['products']), ['seller_ids', 'active'])
        assert_fresh(preflight['products'], {x['id']: x for x in products}, 'Recovery supplier masters')
        chain = self.chain(tid)
        validate_new_chain(chain, live['order_line'])
        # The first interrupted pilot predates persisted counters. Prove absence
        # of any new accounting/MO/PO records since the intent before accepting
        # current counts as the recovery baseline. Never assume a failed RPC
        # means rollback.
        timestamp = datetime.fromisoformat(intent['utc']).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        creations = {model: self.b.scan(model, [['company_id', '=', 1], ['create_date', '>=', timestamp]], ['create_date', 'name']) for model in ('account.move', 'mrp.production', 'purchase.order')}
        if any(creations.values()):
            raise RuntimeError('Records created since intent; counter provenance needs manual review')
        counters = self.counters()
        if entry.get('counters_before') and counters != entry['counters_before']:
            raise RuntimeError('Recovery counters changed')
        evidence = dict(source_id=sid, target_id=tid, operation_id=oid, state=live['state'], chain=chain, products=products, creations_since_intent=creations, counters=counters, checked_utc=datetime.now(timezone.utc).isoformat(), recovery_ready=True, erp_mutations=0)
        save(self.phase / ('confirm-po-recovery-' + str(sid) + '.json'), evidence)
        return preflight, entry, evidence


def validate_new_chain(chain, order_line_ids):
    if any(rid(x['company_id']) != 1 or x['state'] in ('done', 'cancel') for x in chain['pickings'] + chain['moves']):
        raise RuntimeError('Native chain wrong company or already done/cancelled')
    mids = {x['id'] for x in chain['moves']}
    for move in chain['moves']:
        if move.get('picked') or move.get('sale_line_id') or (move.get('purchase_line_id') and rid(move['purchase_line_id']) not in order_line_ids):
            raise RuntimeError('Native chain execution or foreign line detected')
        if not set(move['move_orig_ids']).issubset(mids):
            raise RuntimeError('Native chain has external supply links')
    if any(x.get('picked') or x['state'] == 'done' for x in chain['move_lines']):
        raise RuntimeError('Native move lines already performed')
