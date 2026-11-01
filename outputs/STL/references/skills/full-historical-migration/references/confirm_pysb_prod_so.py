"""Resume frozen production SO confirmation only; no stock validation or approvals."""
import argparse
import hashlib
import json
import os
import runpy
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
C = runpy.run_path(str(BASE / 'run_pysb_phased_migration.py'))
P = runpy.run_path(str(BASE / 'confirm_pysb_prod_orders.py'))
I = P['I']; R = P['R']; W = P['W']; rid = P['rid']; load = P['load']; save = P['save']
H = runpy.run_path(str(BASE / 'hq_mts_delivery_proof.py'))


def now():
    return datetime.now(timezone.utc).isoformat()


def workflow_issues(order, lines, products, partners, categories, units, packages, route_proof, approval_authorized=False):
    issues = []
    if order.get('carrier_id'): issues.append('carrier_requires_review')
    if not approval_authorized and (order.get('x_need_so_approval') or order.get('x_studio_so_approval')): issues.append('native_approval_required')
    if order.get('is_quotation_template'): issues.append('quotation_template')
    if order.get('picking_ids'): issues.append('draft_already_has_pickings')
    for field in ('partner_id', 'partner_invoice_id', 'partner_shipping_id'):
        partner=partners.get(rid(order.get(field)), {})
        historical=route_proof.get('historical_archived_shipping',{}).get(order.get('id'))
        source=route_proof.get('historical_archived_shipping_source',{})
        matching_archived=(field=='partner_shipping_id' and historical==rid(order.get(field)) and partner and not partner.get('active') and source.get('id')==27120 and source.get('active') is False and all((partner.get(f) or False)==(source.get(f) or False) for f in ['name','type','street','street2','city','zip','phone']))
        if not partner.get('active') and not matching_archived: issues.append('archived_or_missing_partner')
    extended=route_proof.get('extended',False)
    if not extended and (rid(order.get('warehouse_id')) != 1 or not route_proof['ready']): issues.append('warehouse_route_unproven')
    if rid(partners.get(rid(order.get('partner_shipping_id')), {}).get('property_stock_customer')) != 2: issues.append('shipping_location_unproven')
    for line in lines:
        if line.get('display_type'): continue
        p = products.get(rid(line.get('product_id')), {})
        if not p.get('active'): issues.append('archived_or_missing_product')
        if not extended and (line.get('route_ids') or line.get('is_expense') or rid(line.get('warehouse_id')) != 1): issues.append('line_procurement_override')
        if p.get('type') != 'service':
            routes = set(p.get('route_ids', [])) | set(categories.get(rid(p.get('categ_id')), {}).get('total_route_ids', []))
            if not routes <= {4, 5}: issues.append('product_route_unproven')
            if line.get('base_price', 0) <= 0 and not line.get('is_free') and not order.get('woo_order_id'): issues.append('zero_base_price_not_free')
        unit = units.get(rid(line.get('product_uom_id')), {})
        package = packages.get(rid(unit.get('package_type_id')), {})
        if not set(package.get('route_ids', [])) <= {3, 4, 5}: issues.append('packaging_route_unproven')
    if extended:
        route_errors,_=runpy.run_path(str(BASE/'production_so_route_proof.py'))['evaluate'](order,lines,products,partners,categories,units,packages,route_proof,route_proof['source_line_route_map'])
        issues.extend(route_errors)
    return sorted(set(issues))


class Run:
    def __init__(self, out):
        self.out = out; self.phase = out / 'phases'
        self.identity, self.readiness = C['validate_context'](out)
        C['require_previous_gate'](out, 'confirm-so', self.identity)
        self.a = I['ReadOnly']('v14-prod', ('http://175.145.85.151', 'paoyeang_live'))
        self.b = I['ReadOnly']('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450'))
        self.log = P['Log'](self.phase, self.identity)
        if self.log.unresolved(): raise RuntimeError('Unresolved RPC; readback required')
        self.approval_authorized = (self.phase / 'operator-so-remediation-approval.json').exists()
        if self.approval_authorized:
            approval = load(self.phase / 'operator-so-remediation-approval.json')
            if approval.get('identity') != self.identity or not approval.get('native_approvals_authorized'): raise RuntimeError('Invalid native approval authorization')
            rules = self.b.scan('studio.approval.rule', [['model_name','=','sale.order'],['method','=','action_confirm'],['active','=',True]], ['can_validate','exclusive_user','domain','message'])
            if not rules or any(not x['can_validate'] or x['exclusive_user'] for x in rules): raise RuntimeError('Current account cannot approve every native SO rule')
            save(self.phase / 'confirm-so-current-approval-rights.json', dict(captured_utc=now(), rules=rules, authorized=True))
        self.maps = {m: {int(k): v for k, v in pairs.items()} for m, pairs in load(out / 'resolved-master-evidence.json')['maps'].items()}
        self.maps, _ = runpy.run_path(str(BASE / 'approved_order_currency_mapping.py'))['apply'](self.maps, self.a.scan('res.currency', [['name', '=', 'CNH']], ['name', 'rounding']), self.b.scan('res.currency', [['name', '=', 'CNY']], ['name', 'rounding']))
        overlaypath=self.out/'so-remediation/applied-overlay.json'
        self.overlay=load(overlaypath) if overlaypath.exists() else {}
        for model,pairs in self.overlay.get('maps',{}).items():self.maps.setdefault(model,{}).update({int(k):v for k,v in pairs.items()})
        self.jpath = self.phase / 'so-confirmation-journal.json'
        self.j = load(self.jpath) if self.jpath.exists() else dict(identity=self.identity, orders={})
        if self.j['identity'] != self.identity: raise RuntimeError('SO journal identity mismatch')
        if any(x['status'] == 'prepared' for x in self.j['orders'].values()): raise RuntimeError('Interrupted SO requires readback')

    def capture(self):
        sources = load(self.phase / 'source-sale.order.json')
        sfields = list(sources[0]); tfields = list(load(self.phase / 'target-sale.order.json')[0])
        sf = list(load(self.phase / 'source-sale.order.line.json')[0])
        tf = list(load(self.phase / 'target-sale.order.line.json')[0])
        self.source = {x['id']: x for x in self.a.read('sale.order', [x['id'] for x in sources], sfields)}
        self.target = {x['id']: x for x in self.b.read('sale.order', [self.maps['sale.order'].get(r['source_id']) for r in self.readiness['models']['sale.order']['rows']], tfields + ['x_need_so_approval', 'x_studio_so_approval', 'is_quotation_template', 'woo_order_id'])}
        self.sl = {x['id']: x for x in self.a.read('sale.order.line', [i for x in self.source.values() for i in x['order_line']], sf)}
        self.tl = {x['id']: x for x in self.b.read('sale.order.line', [i for x in self.target.values() for i in x['order_line']], tf + ['warehouse_id', 'base_price', 'is_free'])}
        products = {x['id']: x for x in self.b.read('product.product', [rid(x.get('product_id')) for x in self.tl.values()], ['active', 'type', 'route_ids', 'categ_id'])}
        partners = {x['id']: x for x in self.b.read('res.partner', [rid(x.get(f)) for x in self.target.values() for f in ['partner_id', 'partner_shipping_id', 'partner_invoice_id']], ['active', 'property_stock_customer','name','type','street','street2','city','zip','phone'])}
        categories = {x['id']: x for x in self.b.read('product.category', [rid(x['categ_id']) for x in products.values()], ['total_route_ids'])}
        units = {x['id']: x for x in self.b.read('uom.uom', [rid(x.get('product_uom_id')) for x in self.tl.values()], ['package_type_id'])}
        packages = {x['id']: x for x in self.b.read('stock.package.type', [rid(x.get('package_type_id')) for x in units.values()], ['route_ids'])}
        route = H['inspect'](self.b)
        if self.overlay.get('extended_route_proof'):
            route=runpy.run_path(str(BASE/'production_so_route_proof.py'))['inspect'](self.b)
            route.update(extended=True,source_line_route_map={int(k):v for k,v in self.overlay['source_line_route_map'].items()})
            route['skip_procurement_order_ids']=self.overlay.get('skip_procurement_order_ids',[])
            if self.overlay.get('historical_archived_shipping'):
                route['historical_archived_shipping']={int(k):v for k,v in self.overlay['historical_archived_shipping'].items()}
                route['historical_archived_shipping_source']=self.a.read('res.partner',[27120],['name','type','active','street','street2','city','zip','phone'])[0]
        automation = runpy.run_path(str(BASE / 'inspect_pysb_stock_automations.py'))['inspect'](self.b)
        if automation['automations_need_review'] or not automation['delivery_communications_disabled']: raise RuntimeError('Automation/communications require review')
        su = {x['id']: x for x in load(self.out / 'source-uom.uom.json')}; tu = {x['id']: x for x in load(self.out / 'target-uom.uom.json')}
        currency = {x['id']: x['rounding'] for x in self.a.read('res.currency', [rid(x['currency_id']) for x in sources], ['rounding'])}
        original = {x['id']: x for x in sources}; rows = []
        for item in self.readiness['models']['sale.order']['rows']:
            s = self.source[item['source_id']]; t = self.target.get(self.maps['sale.order'].get(item['source_id']))
            sl = [self.sl[i] for i in s['order_line']]; tl = [self.tl[i] for i in t['order_line']] if t else []
            end='9999' if s['id'] in self.overlay.get('reviewed_source_header_timestamp_ids',[]) else load(self.out / 'scope.json')['end_utc_exclusive']
            comparison = R['compare_order']('sale.order', s, t, sl, tl, self.maps, su, tu, currency, end)
            issues = comparison['issues'][:]
            if s != original[s['id']]: issues.append(dict(reason='source_changed_since_phase_snapshot'))
            workflow = workflow_issues(t, tl, products, partners, categories, units, packages, route, self.approval_authorized) if t and t['state'] in ['draft', 'sent'] else []
            eligible = comparison['classification'] == 'draft_matched_pending_workflow_preflight' and not issues and not workflow
            rows.append(dict(source_id=s['id'], source_name=s['name'], target_id=t['id'] if t else None, target_state=t['state'] if t else None, eligible=eligible, issues=issues, workflow_issues=workflow, classification=comparison['classification'], date_matches=bool(t and t['date_order'] == s['date_order'])))
        self.rows = rows
        report = dict(identity=self.identity, captured_utc=now(), rows=rows, summary=dict(Counter(x['classification'] for x in rows)), eligible=sum(x['eligible'] for x in rows), workflow_holds=dict(Counter(y for x in rows for y in x['workflow_issues'])), route_proof=route, automation=automation, erp_mutations=0)
        save(self.phase / 'confirm-so-live-preflight.json', report)
        print(json.dumps({k: report[k] for k in ['summary', 'eligible', 'workflow_holds']}), flush=True)
        return report

    def mutate(self, ids, method, args, before):
        oid = self.identity['scope_hash'] + ':sale.order:' + ','.join(map(str, ids)) + ':' + method
        self.log.append_intent(dict(operation_id=oid, phase='confirm-so', source_ids=ids, method=method, args=args, before=before))
        try:
            context=dict(pysb_phase_token=self.token, tz='UTC', tracking_disable=True, mail_notrack=True, mail_create_nolog=True, mail_create_nosubscribe=True, mail_auto_subscribe_no_notify=True, send_email=False)
            if method=='action_confirm' and ids==[65338] and args==[[9481]] and 9481 in self.overlay.get('skip_procurement_order_ids',[]):context['skip_procurement']=True
            result = W['call'](self.b.r, 'sale.order', method, args, {'context': context})
        except Exception:
            self.log.mark_uncertain(oid, 'RPC error; do not retry; readback required')
            raise
        self.log.append_result(oid, dict(returned=True, result=result))
        return result

    def confirm(self, rows):
        tids = [x['target_id'] for x in rows]; sids = [x['source_id'] for x in rows]
        for reader, model, expected in [(self.a, 'sale.order', [self.source[i] for i in sids]), (self.b, 'sale.order', [self.target[i] for i in tids]), (self.a, 'sale.order.line', [self.sl[i] for sid in sids for i in self.source[sid]['order_line']]), (self.b, 'sale.order.line', [self.tl[i] for tid in tids for i in self.target[tid]['order_line']])]:
            actual = reader.read(model, [x['id'] for x in expected], list(expected[0]))
            if {x['id']: x for x in actual} != {x['id']: x for x in expected}: raise RuntimeError('Orders/lines changed before confirmation')
        # Re-read shared procurement metadata once per group, while checking
        # each order and line independently against the same strict MTS proof.
        route = H['inspect'](self.b)
        if self.overlay.get('extended_route_proof'):
            route=runpy.run_path(str(BASE/'production_so_route_proof.py'))['inspect'](self.b)
            route.update(extended=True,source_line_route_map={int(k):v for k,v in self.overlay['source_line_route_map'].items()})
            route['skip_procurement_order_ids']=self.overlay.get('skip_procurement_order_ids',[])
            if self.overlay.get('historical_archived_shipping'):
                route['historical_archived_shipping']={int(k):v for k,v in self.overlay['historical_archived_shipping'].items()}
                route['historical_archived_shipping_source']=self.a.read('res.partner',[27120],['name','type','active','street','street2','city','zip','phone'])[0]
            if 9481 in tids and 9481 in route['skip_procurement_order_ids']:
                proof=load(self.out/'so-remediation/dropship-65338-dependency.json')
                po=self.b.read('purchase.order',[1040],['state','picking_type_id','company_id','dest_address_id','order_line'])[0]
                line=self.b.read('purchase.order.line',[3888],['order_id','product_id','product_qty','product_uom_id'])[0]
                expected=proof['target_purchase_line']
                if po['state'] not in ['draft','sent','purchase','done'] or rid(po['picking_type_id'])!=161 or rid(po['company_id'])!=1 or rid(po['dest_address_id'])!=84080 or any(line[f]!=expected[f] for f in line if f!='id'):raise RuntimeError('Existing dropship PO dependency changed')
        lines = [self.tl[i] for tid in tids for i in self.target[tid]['order_line']]
        products = {x['id']: x for x in self.b.read('product.product', [rid(x.get('product_id')) for x in lines], ['active', 'type', 'route_ids', 'categ_id'])}
        partners = {x['id']: x for x in self.b.read('res.partner', [rid(self.target[t].get(f)) for t in tids for f in ['partner_id', 'partner_invoice_id', 'partner_shipping_id']], ['active', 'property_stock_customer','name','type','street','street2','city','zip','phone'])}
        categories = {x['id']: x for x in self.b.read('product.category', [rid(x['categ_id']) for x in products.values()], ['total_route_ids'])}
        units = {x['id']: x for x in self.b.read('uom.uom', [rid(x.get('product_uom_id')) for x in lines], ['package_type_id'])}
        packages = {x['id']: x for x in self.b.read('stock.package.type', [rid(x.get('package_type_id')) for x in units.values()], ['route_ids'])}
        for tid in tids:
            t = self.target[tid]
            if workflow_issues(t, [self.tl[i] for i in t['order_line']], products, partners, categories, units, packages, route, self.approval_authorized): raise RuntimeError('Live procurement gate changed')
        counts = {m: self.b.call(m, 'search_count', [[['company_id', '=', 1]]]) for m in ['purchase.order', 'mrp.production', 'account.move']}
        for row in rows:
            key = str(row['source_id'])
            if key in self.j['orders'] and self.j['orders'][key]['status'] != 'reopened_after_group_rollback': raise RuntimeError('Previously attempted SO; no repeat')
            self.j['orders'][key] = dict(**row, status='prepared', prepared_utc=now(), before=self.target[row['target_id']], counters_before=counts)
        save(self.jpath, self.j)
        if getattr(self, 'singleton', False):
            result = {}
            for sid, tid in zip(sids, tids):
                result[str(tid)] = self.mutate([sid], 'action_confirm', [[tid]], self.target[tid])
        else:
            result = self.mutate(sids, 'action_confirm', [tids], [self.target[i] for i in tids])
        after = self.b.read('sale.order', tids, ['state', 'date_order', 'picking_ids'])
        for t in after:
            row = next(x for x in rows if x['target_id'] == t['id']); entry = self.j['orders'][str(row['source_id'])]
            entry.update(confirm_result=result, confirmation_readback=t)
            if t['state'] not in ['sale', 'done']:
                entry.update(status='held_native_approval'); save(self.jpath, self.j)
        confirmed = [t for t in after if t['state'] in ['sale', 'done']]
        # Each source date differs; preserve it through individual ORM writes.
        for t in confirmed:
            row = next(x for x in rows if x['target_id'] == t['id']); sid = row['source_id']
            self.mutate([sid], 'write', [[t['id']], {'date_order': self.source[sid]['date_order']}], t)
        for m, count in counts.items():
            if self.b.call(m, 'search_count', [[['company_id', '=', 1]]]) != count: raise RuntimeError('Unexpected procurement/accounting side effect: ' + m)
        final = self.b.read('sale.order', tids, list(self.target[tids[0]]))
        picks = self.b.read('stock.picking', [i for x in final for i in x['picking_ids']], ['name', 'state', 'company_id', 'move_ids', 'sale_id', 'date_done'])
        moves = self.b.read('stock.move', [i for x in picks for i in x['move_ids']], ['state', 'company_id', 'sale_line_id', 'product_id', 'product_uom_qty', 'quantity', 'picked', 'picking_id', 'move_orig_ids', 'move_dest_ids'])
        if any(x['state'] == 'done' or rid(x['company_id']) != 1 for x in picks + moves): raise RuntimeError('Unexpected completed stock/company')
        final_lines = {x['id']: x for x in self.b.read('sale.order.line', [i for t in final for i in t['order_line']], list(self.tl[final[0]['order_line'][0]]))}
        for t in final:
            row = next(x for x in rows if x['target_id'] == t['id']); sid = row['source_id']; entry = self.j['orders'][str(sid)]
            if t['state'] not in ['sale', 'done']: continue
            before = self.target[t['id']]
            for field in ['company_id', 'partner_id', 'partner_invoice_id', 'partner_shipping_id', 'currency_id', 'warehouse_id', 'order_line', 'invoice_ids', 'amount_untaxed', 'amount_tax', 'amount_total']:
                if t[field] != before[field]: raise RuntimeError('SO header changed unexpectedly: ' + field)
            if t['date_order'] != self.source[sid]['date_order']: raise RuntimeError('Historical date mismatch')
            expected = [self.tl[i] for i in t['order_line']]
            actual = [final_lines[i] for i in t['order_line']]
            for a in actual:
                e = self.tl[a['id']]
                if any(a[f] != e[f] for f in e if f not in ['write_date']): raise RuntimeError('Commercial SO line changed: ' + str(a['id']))
            entry.update(status='verified_confirmed', historical_date=t['date_order'], picking_ids=t['picking_ids'], pickings=[p for p in picks if p['id'] in t['picking_ids']], moves=[m for m in moves if rid(m['picking_id']) in t['picking_ids']], verified_utc=now())
        save(self.jpath, self.j); self.log.build_checkpoint()
        print(json.dumps(dict(confirmed=len(confirmed), held=len(rows)-len(confirmed), source_ids=sids)), flush=True)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--evidence-dir', required=True); parser.add_argument('--mode', choices=['preflight', 'sample', 'batch'], default='preflight'); parser.add_argument('--limit', type=int, default=1); parser.add_argument('--all', action='store_true'); parser.add_argument('--singleton', action='store_true'); parser.add_argument('--recover-group-nochange', action='store_true')
    args = parser.parse_args(); out = Path(args.evidence_dir).resolve()
    if not 1 <= args.limit <= 25: raise RuntimeError('Limit must be 1..25')
    lock = runpy.run_path(str(BASE / 'production_write_lock.py'))['acquire'](out)
    try:
        if args.recover_group_nochange:
            identity, readiness = C['validate_context'](out)
            log = P['Log'](out / 'phases', identity)
            unresolved = log.unresolved()
            if len(unresolved) != 1: raise RuntimeError('Expected exactly one unresolved group operation')
            oid = next(iter(unresolved))
            intent = next(e['payload'] for e in log.events if e['kind'] == 'intent' and e['operation_id'] == oid)
            if intent['phase'] != 'confirm-so' or intent['method'] != 'action_confirm' or len(intent['source_ids']) != 2: raise RuntimeError('Not the known two-order failed pilot')
            b = I['ReadOnly']('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450'))
            before = intent['before']; actual = b.read('sale.order', [x['id'] for x in before], list(before[0]))
            if {x['id']: x for x in actual} != {x['id']: x for x in before} or any(x['picking_ids'] or x['state'] not in ['draft', 'sent'] for x in actual): raise RuntimeError('Group outcome differs; no automatic recovery')
            jpath = out / 'phases/so-confirmation-journal.json'; j = load(jpath)
            counters = {m: b.call(m, 'search_count', [[['company_id', '=', 1]]]) for m in ['purchase.order', 'mrp.production', 'account.move']}
            for sid in intent['source_ids']:
                if j['orders'][str(sid)]['counters_before'] != counters: raise RuntimeError('Side-effect counters changed')
            lids = [i for x in before for i in x['order_line']]
            expected = [x for x in load(out / 'phases/target-sale.order.line.json') if x['id'] in lids]
            lines = b.read('sale.order.line', lids, list(expected[0]))
            if {x['id']: x for x in expected} != {x['id']: x for x in lines}: raise RuntimeError('Commercial lines changed')
            moves = b.scan('stock.move', [['sale_line_id', 'in', lids]], ['state', 'picking_id'])
            if moves: raise RuntimeError('Unexpected stock moves; no recovery')
            proof = dict(identity=identity, operation_id=oid, readback_utc=now(), orders=actual, lines=lines, counters=counters, linked_moves=moves, erp_mutations=0, conclusion='Native two-order call failed with singleton Fault; full headers/lines/counters and absence of stock prove no effect. Reopen for separate singleton operations.')
            save(out / 'phases/confirm-so-group-rollback-readback.json', proof)
            log.append_result(oid, dict(returned=False, recovered_by_live_readback=True, no_effect_verified=True, evidence='confirm-so-group-rollback-readback.json'))
            for sid in intent['source_ids']: j['orders'][str(sid)].update(status='reopened_after_group_rollback', failed_group_operation_id=oid)
            save(jpath, j); log.build_checkpoint()
            print(json.dumps(dict(recovered_source_ids=intent['source_ids'], erp_mutations=0, unresolved_operations=len(log.unresolved()))), flush=True)
            return
        runner = Run(out); runner.singleton = args.singleton; runner.capture()
        if args.mode == 'preflight': return
        code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if args.mode == 'sample' and args.limit != 1: raise RuntimeError('Singleton sample first')
        samplepath = out / 'phases/confirm-so-sample.json'
        if args.mode == 'batch':
            sample = load(samplepath)
            if not sample.get('passed') or sample.get('code_hash') != code_hash or sample.get('identity') != runner.identity: raise RuntimeError('Successful current-code sample required')
        if not load(out / 'scope.json').get('backup_acknowledged_by_operator'): raise RuntimeError('Backup acknowledgement missing')
        runner.token = uuid.uuid4().hex
        save(out / 'phases/confirm-so-authorization.json', dict(identity=runner.identity, approved_by='Bruce', instruction='Confirm remaining migrated SO on v19 prod', stock_validation_authorized=False, accounting_authorized=False, recorded_utc=now()))
        save(out / 'phases/phased-control-enabled.json', dict(identity=runner.identity, supported_phases=['confirm-so'], code_hash=code_hash))
        save(out / 'phases/active-phase.json', dict(identity=runner.identity, phase='confirm-so', token=runner.token, pid=os.getpid(), started_utc=now()))
        pending = [x for x in runner.rows if x['eligible'] and (str(x['source_id']) not in runner.j['orders'] or runner.j['orders'][str(x['source_id'])]['status'] == 'reopened_after_group_rollback')]
        selected = []
        while pending:
            # Two-record native pilot before larger recordsets of this code.
            pilot = out / 'phases/confirm-so-recordset-sample.json'
            pilot_ok = pilot.exists() and load(pilot).get('code_hash') == code_hash and load(pilot).get('passed')
            size = args.limit if args.singleton else (min(args.limit, 2) if args.mode == 'batch' and not pilot_ok else args.limit)
            group = pending[:size]
            runner.confirm(group); selected.extend(group); pending = pending[size:]
            if args.mode == 'batch' and not args.singleton and len(group) == 2 and not pilot_ok:
                save(pilot, dict(identity=runner.identity, code_hash=code_hash, passed=all(runner.j['orders'][str(x['source_id'])]['status']=='verified_confirmed' for x in group), source_ids=[x['source_id'] for x in group], completed_utc=now()))
                if not load(pilot)['passed']: break
            if args.mode != 'batch' or not args.all: break
        result = dict(identity=runner.identity, code_hash=code_hash, passed=bool(selected) and all(runner.j['orders'][str(x['source_id'])]['status']=='verified_confirmed' for x in selected), completed_utc=now(), source_ids=[x['source_id'] for x in selected])
        save(samplepath if args.mode == 'sample' else out / 'phases/confirm-so-batch.json', result)
    finally:
        save(out / 'phases/active-phase.json', dict(phase=None, pid=None, token=None, stopped_utc=now()))
        lock.close()


if __name__ == '__main__': main()
