"""Live PO phase verification, complete classification and evidence-bound gate."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import runpy

BASE = Path(__file__).parent
C = runpy.run_path(str(BASE / 'run_pysb_phased_migration.py'))
A = runpy.run_path(str(BASE / 'confirm_pysb_prod_orders.py'))
R = runpy.run_path(str(BASE / 'inspect_pysb_phase_readiness.py'))
rid = R['rid']


def summarize(rows, expected_ids):
    ids = [x['source_id'] for x in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(expected_ids):
        raise RuntimeError('PO verification does not cover the exact frozen order scope')
    if any(x['status'] not in ('verified_confirmed', 'held', 'eligible_unattempted') for x in rows):
        raise RuntimeError('Unclassified PO in gate')
    if any(x['status'] == 'held' and not x.get('reasons') for x in rows):
        raise RuntimeError('Held PO lacks a specific reason')
    done = sum(x['status'] == 'verified_confirmed' for x in rows)
    held = sum(x['status'] == 'held' for x in rows)
    eligible = sum(x['status'] == 'eligible_unattempted' for x in rows)
    return dict(status='in_progress' if eligible else 'closed_with_holds' if held else 'fully_passed', completed_count=done, held_count=held, eligible_unattempted=eligible)


def verify(directory, lock_owned=False):
    directory = Path(directory).resolve()
    lock = None if lock_owned else runpy.run_path(str(BASE / 'production_write_lock.py'))['acquire'](directory)
    try:
        identity, readiness = C['validate_context'](directory)
        runner = A['ConfirmPO'](directory, identity, readiness)
        phase = directory / 'phases'
        source_ids = sorted(runner.source)
        target_ids = sorted(runner.target)
        sf = list(next(iter(runner.source.values())))
        tf = list(next(iter(runner.target.values())))
        sources = {x['id']: x for x in runner.a.read('purchase.order', source_ids, sf)}
        targets = {x['id']: x for x in runner.b.read('purchase.order', target_ids, tf)}
        sl = runner.a.read('purchase.order.line', [i for h in sources.values() for i in h['order_line']], list(next(iter(runner.sl.values()))))
        tl = runner.b.read('purchase.order.line', [i for h in targets.values() for i in h['order_line']], list(next(iter(runner.tl.values()))))
        sg, tg = defaultdict(list), defaultdict(list)
        for line in sl:
            sg[rid(line['order_id'])].append(line)
        for line in tl:
            tg[rid(line['order_id'])].append(line)
        currencies = {x['id']: x['rounding'] for x in runner.a.read('res.currency', {rid(x['currency_id']) for x in sources.values()}, ['rounding'])}
        su = {x['id']: x for x in runner.a.read('uom.uom', {rid(x.get('product_uom') or x.get('product_uom_id')) for x in sl if not x.get('display_type')}, ['rounding'])}
        tu = {x['id']: x for x in runner.b.read('uom.uom', {rid(x.get('product_uom_id') or x.get('product_uom')) for x in tl if not x.get('display_type')}, ['rounding'])}
        picks = runner.b.read('stock.picking', [i for h in targets.values() for i in h.get('picking_ids', [])], ['state', 'company_id', 'move_ids', 'date_done'])
        pi = {x['id']: x for x in picks}
        moves = {}
        frontier = {i for p in picks for i in p['move_ids']}
        fields = 'company_id state product_id product_uom product_uom_qty quantity picked purchase_line_id sale_line_id picking_id move_orig_ids move_dest_ids move_line_ids location_id location_dest_id'.split()
        while frontier:
            batch = runner.b.read('stock.move', frontier, fields)
            moves.update({x['id']: x for x in batch})
            frontier = {i for m in batch for i in m['move_dest_ids']} - set(moves)
        ml = {x['id']: x for x in runner.b.read('stock.move.line', [i for m in moves.values() for i in m['move_line_ids']], ['move_id', 'state', 'picked', 'quantity', 'lot_id', 'package_id', 'owner_id'])}
        scope = C['load'](directory / 'scope.json')
        rows = []
        eligible = 0
        for old in readiness['models']['purchase.order']['rows']:
            sid, tid = old['source_id'], old['target_id']
            s, t = sources[sid], targets.get(tid)
            comparison = R['compare_order']('purchase.order', s, t, sg[sid], tg[tid], runner.maps, su, tu, currencies, scope['end_utc_exclusive'])
            reasons = list(comparison['issues'])
            key = 'purchase.order:' + str(sid)
            own = runner.j['orders'].get(key, {})
            status = 'held'
            if s != runner.source[sid]:
                reasons.append({'reason': 'source_changed_since_M0'})
            if t and t['state'] == 'purchase' and not reasons:
                if t.get('date_approve') != s.get('date_approve'):
                    reasons.append({'reason': 'historical_approval_date_mismatch', 'source': s.get('date_approve'), 'target': t.get('date_approve')})
                order_picks = [pi[i] for i in t.get('picking_ids', [])]
                owned = {i for p in order_picks for i in p['move_ids']}
                frontier = set(owned)
                while frontier:
                    following = {i for mid in frontier for i in moves[mid]['move_dest_ids']} - owned
                    owned.update(following)
                    frontier = following
                chain_moves = [moves[i] for i in sorted(owned)]
                if any(rid(m['company_id']) != 1 or (m.get('purchase_line_id') and rid(m['purchase_line_id']) not in t['order_line']) or m.get('sale_line_id') for m in chain_moves):
                    reasons.append({'reason': 'native_chain_wrong_company_or_foreign_order_line'})
                for m in chain_moves:
                    pol = rid(m.get('purchase_line_id'))
                    if pol:
                        target_line = next(x for x in tg[tid] if x['id'] == pol)
                        if rid(m['product_id']) != rid(target_line['product_id']):
                            reasons.append({'reason': 'native_move_product_differs_from_PO_line', 'target_move': m['id']})
                if not reasons:
                    status = 'verified_confirmed'
                    chain = dict(order_line_ids=t['order_line'], pickings=order_picks, moves=chain_moves, move_lines=[ml[i] for m in chain_moves for i in m['move_line_ids']])
                    if key not in runner.chains['orders']:
                        runner.chains['orders'][key] = dict(source_model='purchase.order', source_id=sid, target_id=tid, provenance='preexisting_verified', after=chain, after_hash=R['digest'](chain), line_mappings={str(x['id']): runner.maps.get('purchase.order.line', {}).get(x['id']) for x in sg[sid]}, preparation_authorized=False, note='Verified PO identity, commercial content, historical approval date and native line links; stock details must be verified separately before preparation or reservation changes.')
            elif t and t['state'] in ('draft', 'sent') and not reasons:
                if own.get('status') in ('held_workflow', 'held_native_approval'):
                    reasons.extend({'reason': x} for x in own.get('reasons', []))
                else:
                    eligible += 1
                    status = 'eligible_unattempted'
            if status == 'held' and not reasons:
                reasons.append({'reason': comparison['classification']})
            rows.append(dict(source_id=sid, target_id=tid, source_name=s['name'], target_name=t.get('name') if t else None, source_state=s['state'], target_state=t.get('state') if t else None, status=status, reasons=reasons, line_results=comparison['line_results']))
        # Ensure this read capture did not straddle order edits.
        for reader, model_rows in ((runner.a, sources), (runner.b, targets)):
            check = reader.read('purchase.order', list(model_rows), ['write_date'])
            if any(x['write_date'] != model_rows[x['id']]['write_date'] for x in check):
                raise RuntimeError('Orders changed during verification; gate not written')
        runner.persist()
        runner.log.build_checkpoint()
        report = dict(identity=identity, captured_utc=datetime.now(timezone.utc).isoformat(), read_only_erp=True, rows=rows, total=len(rows), unclassified=0)
        A['save'](phase / 'confirm-po-verification.json', report)
        expected_ids = [x['source_id'] for x in C['load'](phase / 'phase-scope.json')['purchase.order']]
        summary = summarize(rows, expected_ids)
        evidence_files = ['confirm-po-verification.json', 'native-chain-index.json', 'order-confirmation-journal.json', 'order-currency-map-evidence.json']
        gate = dict(identity, phase='confirm-po', **summary, live_verification_complete=True, completed_utc=report['captured_utc'], evidence=[dict(path='phases/' + name, sha256=hashlib.sha256((phase / name).read_bytes()).hexdigest()) for name in evidence_files])
        A['save'](phase / 'confirm-po-gate.json', gate)
        print(__import__('json').dumps(gate, ensure_ascii=True), flush=True)
        return gate
    finally:
        if lock is not None:
            lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-dir', required=True)
    verify(parser.parse_args().evidence_dir)
