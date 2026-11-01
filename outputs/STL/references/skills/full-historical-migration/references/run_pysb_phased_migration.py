"""Phase controller. Unimplemented execution adapters fail closed."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

BASE = Path(__file__).parent
PHASES = ('confirm-po', 'confirm-so', 'stock', 'accounting', 'verify')


def code_hashes():
    names = ('run_pysb_phased_migration.py', 'confirm_pysb_prod_orders.py', 'production_operation_log.py', 'production_phase_guard.py', 'production_workflow_rpc.py', 'approved_order_currency_mapping.py')
    return {name: hashlib.sha256((BASE / name).read_bytes()).hexdigest() for name in names}


def execute_po(directory, identity, readiness, mode, limit, finish_confirmed=None, recordset=False):
    module = runpy.run_path(str(BASE / 'confirm_pysb_prod_orders.py'))
    save = module['save']
    phase = directory / 'phases'
    validated_hashes = code_hashes()
    if mode == 'batch':
        sample = load(phase / ('confirm-po-recordset-sample.json' if recordset else 'confirm-po-sample.json'))
        if sample.get('identity') != identity or sample.get('code_hashes') != code_hashes() or not sample.get('passed'):
            raise RuntimeError('Current code requires a successful PO production sample before batch')
    if mode == 'sample' and limit != (2 if recordset else 1):
        raise RuntimeError('Production sample requires one singleton PO or two recordset PO')
    if limit > 25:
        raise RuntimeError('PO confirmation batch limit is 25')
    # Actual offline validation, recorded with code hashes before enabling writes.
    tested = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(BASE / 'tests'), '-q'], capture_output=True, text=True)
    save(phase / 'offline-validation.json', dict(captured_utc=datetime.now(timezone.utc).isoformat(), returncode=tested.returncode, output=tested.stdout + tested.stderr, code_hashes=code_hashes()))
    if tested.returncode:
        raise RuntimeError('Offline safety tests failed; no mutation sent')
    if code_hashes() != validated_hashes:
        raise RuntimeError('Code changed during validation; no mutation sent')
    runner = module['ConfirmPO'](directory, identity, readiness, recovery=bool(finish_confirmed))
    incomplete = [key for key, row in runner.j['orders'].items() if row.get('status') not in ('verified_confirmed', 'held_workflow', 'held_native_approval', 'reopened_workflow_preflight')]
    if incomplete and not finish_confirmed:
        raise RuntimeError('Prior confirmation requires readback recovery: ' + ','.join(incomplete))
    scope = load(directory / 'scope.json')
    if not scope.get('backup_acknowledged_by_operator'):
        raise RuntimeError('Production backup acknowledgement missing')
    token = uuid.uuid4().hex
    enabled = dict(identity=identity, supported_phases=['confirm-po'], approved_plan_sha256=load(directory / 'execplan-approval.json')['approved_plan_sha256'], code_hashes=code_hashes(), status='PO pilot; later adapters remain disabled')
    if (phase / 'phased-control-enabled.json').exists():
        old = load(phase / 'phased-control-enabled.json')
        if old['identity'] != identity:
            raise RuntimeError('Enabled controller belongs to another scope')
    save(phase / 'phased-control-enabled.json', enabled)
    save(phase / 'active-phase.json', dict(identity=identity, phase='confirm-po', token=token, pid=os.getpid(), started_utc=datetime.now(timezone.utc).isoformat()))
    runner.session_token = token
    completed = []
    held = []
    selected = []
    started = time.perf_counter()
    try:
        if finish_confirmed:
            if mode != 'sample':
                raise RuntimeError('Targeted recovery must use sample mode')
            preflight, entry, evidence = runner.inspect_recovery(finish_confirmed)
            runner.log.append_result(evidence['operation_id'], dict(returned=False, recovered_by_live_readback=True, evidence_file='confirm-po-recovery-' + str(finish_confirmed) + '.json', state='purchase'))
            entry['confirm_operation_id'] = evidence['operation_id']
            runner.persist()
            row = next(r for r in readiness['models']['purchase.order']['rows'] if r['source_id'] == finish_confirmed)
            result = runner.finish_confirmed(row, preflight, entry, evidence['counters'])
            completed.append(result)
            print(json.dumps(dict(source_id=finish_confirmed, target_id=row['target_id'], confirmed=True, confirmation_repeated=False, warehouse_done_by_this_phase=0, new_invoices=0, native_chain_ids=result['native_chain_ids'])), flush=True)
        for row in readiness['models']['purchase.order']['rows']:
            if len(completed) >= limit:
                break
            if row['classification'] != 'draft_matched_pending_workflow_preflight':
                continue
            key = 'purchase.order:' + str(row['source_id'])
            if key in runner.j['orders'] and runner.j['orders'][key].get('status') != 'reopened_workflow_preflight':
                continue
            preflight = runner.preflight(row)
            if preflight['issues']:
                runner.j['orders'][key] = dict(source_model='purchase.order', source_id=row['source_id'], target_id=row['target_id'], status='held_workflow', reasons=preflight['issues'])
                runner.persist()
                held.append(row['source_id'])
                continue
            if recordset:
                selected.append((row, preflight))
                if len(selected) >= limit:
                    break
                continue
            result = runner.confirm(row, preflight)
            completed.append(result)
            print(json.dumps(dict(source_id=row['source_id'], target_id=row['target_id'], confirmed=True, warehouse_done_by_this_phase=0, new_invoices=0, native_chain_ids=result['native_chain_ids'])), flush=True)
            if len(completed) >= limit:
                break
        native_calls = len(completed)
        if selected:
            if len(selected) == 1:
                if mode == 'sample':
                    raise RuntimeError('Not enough eligible PO for a two-order recordset pilot')
                completed.append(runner.confirm(*selected[0]))
                native_calls = 1
            else:
                group_result = runner.confirm_recordset(selected)
                completed.extend(group_result['completed'])
                held.extend(x['source_id'] for x in group_result['held'])
                native_calls = group_result['native_confirm_rpc_calls']
            print(json.dumps(dict(recordset=recordset, confirmed=len(completed), native_confirm_rpc_calls=native_calls, target_ids=[r['target_id'] for r in completed], held_source_ids=held, warehouse_done_by_this_phase=0, new_invoices=0)), flush=True)
        result = dict(identity=identity, mode=mode, recordset=recordset, native_confirm_rpc_calls=native_calls, code_hashes=validated_hashes, code_changed_during_run=code_hashes() != validated_hashes, passed=bool(completed) and (not recordset or len(completed) == len(selected)) and code_hashes() == validated_hashes, completed=completed, held_source_ids=held, elapsed_seconds=time.perf_counter() - started, completed_utc=datetime.now(timezone.utc).isoformat())
        artifact = phase / ('confirm-po-' + ('recordset-' if recordset else '') + mode + '.json')
        history = phase / 'runs'
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        if artifact.exists():
            save(history / (artifact.stem + '-previous-' + stamp + '.json'), load(artifact))
        save(artifact, result)
        save(history / (artifact.stem + '-' + stamp + '.json'), result)
        save(phase / 'performance-pilot.json', dict(identity=identity, kind='PO confirmation', documents=len(completed), elapsed_seconds=result['elapsed_seconds'], comparison_available=False, note='No equivalent confirmation baseline exists; no speedup claim.'))
        return result
    finally:
        save(phase / 'active-phase.json', dict(identity=identity, phase=None, pid=None, token=None, stopped_utc=datetime.now(timezone.utc).isoformat()))


def load(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def validate_context(directory):
    directory = Path(directory)
    approval = load(directory / 'execplan-approval.json')
    frozen_hash = hashlib.sha256((directory / 'scope.json').read_bytes()).hexdigest()
    if not approval.get('approved') or approval['scope_sha256'] != frozen_hash:
        raise RuntimeError('Frozen scope is not approved')
    snapshot = BASE.parents[5] / approval['approved_snapshot']
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != approval['approved_plan_sha256']:
        raise RuntimeError('Approved plan snapshot changed')
    scope = load(directory / 'phases/phase-scope.json')
    readiness = load(directory / 'phases/phase-readiness.json')
    identity = dict(source_database='paoyeang_live', target_database='py19-main-33843450', company_id=1, scope_hash=scope['scope_hash'])
    for key, value in identity.items():
        if scope.get(key) != value or readiness.get(key) != value:
            raise RuntimeError('Phase identity mismatch: ' + key)
    expected = runpy.run_path(str(BASE / 'inspect_pysb_phase_readiness.py'))['digest']({k: v for k, v in scope.items() if k != 'scope_hash'})
    if expected != scope['scope_hash'] or readiness.get('unclassified') != 0:
        raise RuntimeError('Invalid scope checksum or unclassified orders')
    if not readiness.get('read_only') or readiness.get('completed_utc') is None:
        raise RuntimeError('M0 capture incomplete')
    for path in directory.glob('*journal.json'):
        journal = load(path)
        operations = journal.get('operations', []) if isinstance(journal, dict) else []
        if any(x.get('status') in ('intent', 'uncertain') for x in operations):
            raise RuntimeError('Unresolved historical mutation: ' + path.name)
    return identity, readiness


def require_previous_gate(directory, phase, identity):
    index = PHASES.index(phase)
    if index == 0:
        return None
    previous = PHASES[index - 1]
    gate = load(Path(directory) / 'phases' / (previous + '-gate.json'))
    if any(gate.get(k) != v for k, v in identity.items()):
        raise RuntimeError('Previous gate belongs to another scope/database/company')
    if gate.get('phase') != previous or gate.get('status') not in ('fully_passed', 'closed_with_holds') or gate.get('eligible_unattempted') != 0:
        raise RuntimeError('Previous phase is not closed')
    if not gate.get('completed_utc') or not gate.get('evidence') or not gate.get('live_verification_complete'):
        raise RuntimeError('Previous gate lacks live verification evidence')
    for evidence in gate['evidence']:
        path = Path(directory) / evidence['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != evidence['sha256']:
            raise RuntimeError('Previous gate evidence changed')
    return gate


def build_plan(phase, identity, readiness):
    model = {'confirm-po': 'purchase.order', 'confirm-so': 'sale.order'}.get(phase)
    rows = readiness['models'][model]['rows'] if model else []
    return dict(schema_version=1, **identity, phase=phase, mode='plan', erp_mutations=0,
                readiness_captured_utc=readiness['completed_utc'],
                total=len(rows), commercial_candidates=[r['source_id'] for r in rows if r['classification'] == 'draft_matched_pending_workflow_preflight'],
                workflow_preflight_complete=False, execution_adapter_ready=False,
                note='Commercial candidates require live workflow checks; this plan does not close any phase.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=PHASES, required=True)
    parser.add_argument('--mode', choices=('plan', 'sample', 'batch', 'verify'), required=True)
    parser.add_argument('--limit', type=int, default=1)
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--live-preflight', action='store_true')
    parser.add_argument('--inspect-recovery', type=int)
    parser.add_argument('--finish-confirmed', type=int)
    parser.add_argument('--recordset', action='store_true')
    parser.add_argument('--recheck-supplier-holds', action='store_true')
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    directory = Path(args.evidence_dir).resolve()
    lock = runpy.run_path(str(BASE / 'production_write_lock.py'))['acquire'](directory)
    try:
        identity, readiness = validate_context(directory)
        if args.phase == 'confirm-po' and args.mode == 'plan' and args.recheck_supplier_holds:
            module = runpy.run_path(str(BASE / 'confirm_pysb_prod_orders.py'))
            runner = module['ConfirmPO'](directory, identity, readiness)
            print(json.dumps(dict(reopened=runner.recheck_supplier_holds(), erp_mutations=0)), flush=True)
            return
        if (directory / 'phases/operator-stop-after-confirm-po.json').exists() and args.phase != 'confirm-po' and args.mode != 'plan':
            raise RuntimeError('Bruce requested stopping after PO confirmation; later phases are not authorized for this run')
        if args.phase == 'confirm-po' and args.mode == 'verify':
            runpy.run_path(str(BASE / 'verify_pysb_phase_orders.py'))['verify'](directory, lock_owned=True)
            return
        if args.phase == 'confirm-po' and args.mode == 'plan' and args.inspect_recovery:
            module = runpy.run_path(str(BASE / 'confirm_pysb_prod_orders.py'))
            runner = module['ConfirmPO'](directory, identity, readiness, recovery=True)
            _, _, evidence = runner.inspect_recovery(args.inspect_recovery)
            print(json.dumps({k: v for k, v in evidence.items() if k not in ('chain', 'products')}, ensure_ascii=True))
            return
        if args.phase == 'confirm-po' and args.mode in ('sample', 'batch'):
            execute_po(directory, identity, readiness, args.mode, args.limit, args.finish_confirmed, args.recordset)
            return
        if args.phase == 'confirm-po' and args.mode == 'plan' and args.live_preflight:
            module = runpy.run_path(str(BASE / 'confirm_pysb_prod_orders.py'))
            runner = module['ConfirmPO'](directory, identity, readiness)
            rows = []
            candidates = [r for r in readiness['models']['purchase.order']['rows'] if r['classification'] == 'draft_matched_pending_workflow_preflight']
            for row in candidates[:args.limit]:
                key = 'purchase.order:' + str(row['source_id'])
                if key in runner.j['orders']:
                    rows.append(dict(source_id=row['source_id'], target_id=row['target_id'], prior_status=runner.j['orders'][key]['status']))
                    continue
                preflight = runner.preflight(row)
                rows.append(dict(source_id=row['source_id'], target_id=row['target_id'], issues=preflight['issues'], before_chain=preflight['before_chain'], eligible=not preflight['issues']))
                print(json.dumps(dict(source_id=row['source_id'], preflight_issues=preflight['issues'], erp_mutations=0)), flush=True)
            module['save'](directory / 'phases/confirm-po-live-preflight.json', dict(identity=identity, captured_utc=datetime.now(timezone.utc).isoformat(), rows=rows, erp_mutations=0))
            return
        if args.mode != 'plan':
            require_previous_gate(directory, args.phase, identity)
            raise RuntimeError('Execution adapter not yet validated; no ERP mutation was sent')
        result = build_plan(args.phase, identity, readiness)
        path = directory / 'phases' / (args.phase + '-plan.json')
        temp = path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
        temp.replace(path)
        print(json.dumps({k: v for k, v in result.items() if k != 'commercial_candidates'}, ensure_ascii=True))
    finally:
        lock.close()


if __name__ == '__main__':
    main()
