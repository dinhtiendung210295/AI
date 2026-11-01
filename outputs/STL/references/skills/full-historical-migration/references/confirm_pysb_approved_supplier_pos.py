"""Confirm only the eight PO whose native supplier additions Bruce approved."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import uuid
from datetime import datetime, timezone

BASE = Path(__file__).parent
C = runpy.run_path(str(BASE / 'run_pysb_phased_migration.py'))
P = runpy.run_path(str(BASE / 'confirm_pysb_prod_orders.py'))
rid, save, load = P['rid'], P['save'], P['load']
INFO_FIELDS = ['partner_id', 'product_tmpl_id', 'product_id', 'currency_id', 'price', 'discount', 'min_qty', 'delay', 'company_id', 'product_uom_id', 'write_date']


def validate_delta(before, after, old_info, current_info, products, allowed_products, vendor, currency):
    before = {int(k): v for k, v in before.items()}
    after = {x['id']: x for x in after}
    if set(before) != set(after):
        raise RuntimeError('Supplier verification product set changed')
    added = set()
    for pid, old in before.items():
        new = after[pid]
        if old['active'] != new['active'] or not set(old['seller_ids']).issubset(new['seller_ids']):
            raise RuntimeError('Existing supplier link removed or product archive state changed')
        extra = set(new['seller_ids']) - set(old['seller_ids'])
        if extra and pid not in allowed_products:
            raise RuntimeError('Supplier addition outside approved product set')
        added.update(extra)
    for sid, original in old_info.items():
        if current_info.get(int(sid)) != original:
            raise RuntimeError('Existing supplier metadata changed')
    for sid in added:
        info = current_info[sid]
        templates = {rid(products[pid]['product_tmpl_id']) for pid in allowed_products}
        if rid(info['partner_id']) != vendor or rid(info['product_tmpl_id']) not in templates or rid(info['currency_id']) != currency or rid(info.get('company_id')) not in (False, 1):
            raise RuntimeError('Created supplier link has unapproved vendor/template/currency/company')
        if info.get('product_id') and rid(info['product_id']) not in allowed_products:
            raise RuntimeError('Created supplier link has an unapproved variant')
        if info.get('min_qty') != 1 or info.get('delay') != 0:
            raise RuntimeError('Native supplier minimum quantity or lead time unexpected')
    return sorted(added)


class ApprovedPO(P['ConfirmPO']):
    def __init__(self, directory, identity, readiness, approval):
        self.approval = approval
        self.allowed = {x['source_id']: x for x in approval['orders']}
        super().__init__(directory, identity, readiness)

    def preflight(self, row):
        allowed = self.allowed.get(row['source_id'])
        if not allowed or allowed['target_id'] != row['target_id']:
            raise RuntimeError('PO outside the eight approved orders')
        value = super().preflight(row)
        for issue in value['issues']:
            if issue.startswith('confirmation_may_create_supplier_master:'):
                lid = int(issue.split(':')[1])
                line = next(x for x in value['target_lines'] if x['id'] == lid)
                if lid not in allowed['target_line_ids'] or rid(line['product_id']) not in allowed['target_product_ids']:
                    raise RuntimeError('Supplier addition no longer matches approved line/product')
        value['issues'] = [x for x in value['issues'] if not x.startswith('confirmation_may_create_supplier_master:')]
        partner = self.b.read('res.partner', [rid(value['target']['partner_id'])], ['parent_id'])[0]
        vendor = rid(partner['parent_id']) or partner['id']
        if vendor not in allowed['vendor_ids']:
            raise RuntimeError('Approved vendor identity changed')
        products = {x['id']: x for x in self.b.read('product.product', list(value['products']), ['product_tmpl_id', 'uom_id'])}
        old_ids = {i for x in value['products'].values() for i in x['seller_ids']}
        old_info = {x['id']: x for x in self.b.read('product.supplierinfo', old_ids, INFO_FIELDS)}
        value['approved_supplier_changes'] = dict(approval_sha256=P['digest'](self.approval), allowed_products=allowed['target_product_ids'], vendor=vendor, currency=rid(value['target']['currency_id']), products=products, old_info=old_info,
                                                counts={m: self.b.call(m, 'search_count', [[]]) for m in ('res.partner', 'product.supplierinfo')})
        return value

    def verify_supplier_changes(self, preflight, products_after, entry):
        proof = preflight['approved_supplier_changes']
        ids = {i for x in products_after for i in x['seller_ids']}
        info = {x['id']: x for x in self.b.read('product.supplierinfo', ids, INFO_FIELDS)}
        added = validate_delta(preflight['products'], products_after, proof['old_info'], info, proof['products'], set(proof['allowed_products']), proof['vendor'], proof['currency'])
        counts = {m: self.b.call(m, 'search_count', [[]]) for m in ('res.partner', 'product.supplierinfo')}
        if counts['res.partner'] != proof['counts']['res.partner'] or counts['product.supplierinfo'] != proof['counts']['product.supplierinfo'] + len(added):
            raise RuntimeError('Unexpected contact or supplier record count change')
        entry['approved_supplier_changes'] = dict(approval_sha256=proof['approval_sha256'], created_supplier_ids=added, created_suppliers=[info[i] for i in added], before_products=preflight['products'], after_products=products_after, existing_supplier_metadata_unchanged=True, new_contacts=0)
        self.persist()


def main(directory, mode):
    directory = Path(directory).resolve()
    phase = directory / 'phases'
    lock = runpy.run_path(str(BASE / 'production_write_lock.py'))['acquire'](directory)
    old_enabled = None
    active_set = False
    try:
        identity, readiness = C['validate_context'](directory)
        approval = load(phase / 'approved-eight-po-supplier-links.json')
        if not approval.get('approved') or approval['scope_identity'] != identity or len(approval['orders']) != 8:
            raise RuntimeError('Exact eight-PO approval missing')
        code_hash = P['digest']({name: hashlib.sha256((BASE / name).read_bytes()).hexdigest() for name in ('confirm_pysb_approved_supplier_pos.py', 'confirm_pysb_prod_orders.py', 'production_operation_log.py', 'production_workflow_rpc.py')})
        if mode == 'batch':
            sample = load(phase / 'approved-supplier-po-sample.json')
            if not sample.get('passed') or sample['code_hash'] != code_hash or sample['approval_sha256'] != P['digest'](approval):
                raise RuntimeError('Approved supplier workflow requires a current successful sample')
        tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(BASE / 'tests'), '-q'], capture_output=True, text=True)
        save(phase / 'approved-supplier-offline-tests.json', dict(returncode=tests.returncode, output=tests.stdout + tests.stderr, code_hash=code_hash))
        if tests.returncode:
            raise RuntimeError('Offline tests failed; no production mutation sent')
        runner = ApprovedPO(directory, identity, readiness, approval)
        old_enabled = load(phase / 'phased-control-enabled.json')
        token = uuid.uuid4().hex
        save(phase / 'phased-control-enabled.json', dict(identity=identity, supported_phases=['confirm-po'], code_hash=code_hash, supplier_approval=P['digest'](approval)))
        save(phase / 'active-phase.json', dict(identity=identity, phase='confirm-po', pid=os.getpid(), token=token, started_utc=datetime.now(timezone.utc).isoformat()))
        active_set = True
        runner.session_token = token
        completed = []
        history = phase / 'history'
        history.mkdir(exist_ok=True)
        save(history / ('before-approved-eight-suppliers-' + mode + '.json'), runner.j)
        for sid, allowed in runner.allowed.items():
            key = 'purchase.order:' + str(sid)
            previous = runner.j['orders'][key]
            if previous['status'] == 'verified_confirmed':
                continue
            if previous['status'] != 'held_workflow' or not runner.never_attempted(sid):
                raise RuntimeError('Approved supplier PO already has a mutation or incomplete state')
            row = next(x for x in readiness['models']['purchase.order']['rows'] if x['source_id'] == sid)
            preflight = runner.preflight(row)
            if preflight['issues']:
                raise RuntimeError('Another workflow issue blocks approved supplier PO: ' + str(preflight['issues']))
            runner.j['orders'][key] = dict(source_model='purchase.order', source_id=sid, target_id=allowed['target_id'], status='reopened_workflow_preflight', prior_workflow_hold=copy.deepcopy(previous), supplier_approval=P['digest'](approval))
            runner.persist()
            result = runner.confirm(row, preflight)
            completed.append(result)
            print(json.dumps(dict(source_id=sid, target_id=allowed['target_id'], confirmed=True, created_supplier_ids=result['approved_supplier_changes']['created_supplier_ids'], new_contacts=0, warehouse_done_by_this_phase=0, new_invoices=0)), flush=True)
            if mode == 'sample':
                break
        result = dict(passed=bool(completed), code_hash=code_hash, approval_sha256=P['digest'](approval), completed=completed, completed_utc=datetime.now(timezone.utc).isoformat())
        save(phase / ('approved-supplier-po-' + mode + '.json'), result)
    finally:
        if active_set:
            save(phase / 'active-phase.json', dict(identity=identity, phase=None, pid=None, token=None, stopped_utc=datetime.now(timezone.utc).isoformat()))
        if old_enabled is not None:
            save(phase / 'phased-control-enabled.json', old_enabled)
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--mode', choices=['sample', 'batch'], required=True)
    args = parser.parse_args()
    main(args.evidence_dir, args.mode)
