"""Read-only production SO/PO quantity reconciliation with outside-period evidence."""
import argparse
import json
import runpy
import socket
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
I = runpy.run_path(str(BASE / 'inspect_pysb_aug_oct_prod.py'))
C = runpy.run_path(str(BASE / 'order_quantity_checks.py'))
ReadOnly, ROOT = I['ReadOnly'], I['ROOT']
rid = C['rid']

def run(evidence):
    socket.setdefaulttimeout(120)
    scope = json.loads((evidence / 'scope.json').read_text(encoding='utf8'))
    if not scope.get('complete'):
        raise RuntimeError('Source snapshot incomplete')
    a = ReadOnly('v14-prod', ('http://175.145.85.151', 'paoyeang_live'))
    b = ReadOnly('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450'))
    xids = b.scan('ir.model.data', [['module', '=', 'pysb_v14']], ['model', 'name', 'res_id'])
    maps, conflicts = defaultdict(dict), []
    for x in xids:
        prefix = x['model'].replace('.', '_') + '_'
        suffix = x['name'][len(prefix):] if x['name'].startswith(prefix) else ''
        if not suffix.isdigit():
            continue
        sid = int(suffix)
        if sid in maps[x['model']] and maps[x['model']][sid] != x['res_id']:
            conflicts.append({'model': x['model'], 'source_id': sid})
        maps[x['model']][sid] = x['res_id']
    # Master identities come from original external IDs, including preserved
    # v14 namespaces, and explicit product-delta provenance; never from names.
    for model in ['product.product', 'uom.uom']:
        sx = a.scan('ir.model.data', [['model', '=', model]], ['module', 'name', 'res_id'])
        tx = b.scan('ir.model.data', [['model', '=', model]], ['module', 'name', 'res_id'])
        target_ids = defaultdict(set)
        candidates = defaultdict(set)
        for x in tx:
            target_ids[x['module'] + '.' + x['name']].add(x['res_id'])
            prefix = model.replace('.', '_') + '_'
            if x['module'] == 'product_delta_v14_paoyeang_live' and x['name'].startswith(prefix) and x['name'][len(prefix):].isdigit():
                candidates[int(x['name'][len(prefix):])].add(x['res_id'])
        for x in sx:
            for prefix in ['', 'v14_', 'v14_v2_']:
                candidates[x['res_id']].update(target_ids[prefix + x['module'] + '.' + x['name']])
        for sid, tids in candidates.items():
            if sid in maps[model]:
                tids.add(maps[model][sid])
            if len(tids) == 1:
                maps[model][sid] = next(iter(tids))
            elif len(tids) > 1:
                maps[model].pop(sid, None)
                conflicts.append({'model': model, 'source_id': sid, 'targets': sorted(tids)})
    moves = json.loads((evidence / 'source-moves.json').read_text(encoding='utf8'))
    invoices = json.loads((evidence / 'source-invoice-lines.json').read_text(encoding='utf8'))
    frozen_invoice_ids={x['id'] for x in json.loads((evidence/'source-invoices.json').read_text(encoding='utf8'))}
    frozen_move_ids={x['id'] for x in moves}
    resolved_path = evidence / 'resolved-master-evidence.json'
    if resolved_path.exists():
        resolved = json.loads(resolved_path.read_text(encoding='utf8'))
        rejected = {(x['model'],x['source_id'],x['rejected_target_id'],x['target_id']) for x in resolved['resolutions'] if 'rejected_target_id' in x}
        for model in ['product.product', 'uom.uom']:
            for sid, tid in resolved['maps'].get(model, {}).items():
                sid = int(sid)
                if sid in maps[model] and maps[model][sid] != tid:
                    if (model,sid,maps[model][sid],tid) in rejected: maps[model][sid] = tid
                    else: conflicts.append({'model': model, 'source_id': sid, 'targets': [maps[model][sid], tid]})
                else:
                    maps[model][sid] = tid
    blocked_units={x['source_id'] for x in resolved.get('issues',[]) if x['model']=='uom.uom'} if resolved_path.exists() else set()
    for sid in blocked_units:maps['uom.uom'].pop(sid,None)
    report = {'database': b.r.db, 'scope': scope, 'started_utc':datetime.now(timezone.utc).isoformat(),'quantity_basis':'Live source/target order quantities; documents outside the frozen transaction snapshot are separately listed, without extending write scope.', 'mapping_conflicts': conflicts, 'models': [], 'dependencies': {}}
    for model, order_model, link in [('sale.order.line', 'sale.order', 'sale_line_id'), ('purchase.order.line', 'purchase.order', 'purchase_line_id')]:
        orders = a.scan(order_model, [['company_id', '=', 1], ['state', 'in', ['sale', 'done'] if order_model == 'sale.order' else ['purchase', 'done']], ['date_order', '>=', scope['start_utc']], ['date_order', '<', scope['end_utc_exclusive']]], ['name', 'order_line', 'state', 'date_order'])
        line_ids = {i for o in orders for i in o['order_line']}
        line_ids.update(rid(x.get(link)) for x in moves if x.get(link))
        for inv in invoices:
            line_ids.update(inv.get('sale_line_ids', []) if model == 'sale.order.line' else [rid(inv.get('purchase_line_id'))])
        line_ids.discard(False)
        fields = 'order_id display_type product_id product_uom product_uom_id product_uom_qty product_qty qty_delivered qty_received qty_invoiced invoice_lines move_ids'.split()
        source = a.read(model, line_ids, fields)
        target = b.read(model, [maps[model][i] for i in line_ids if i in maps[model]], fields)
        su = {rid(x.get('product_uom_id') or x.get('product_uom')) for x in source}
        tu = {rid(x.get('product_uom_id') or x.get('product_uom')) for x in target}
        su.discard(False); tu.discard(False)
        source_uoms = {x['id']: x for x in a.read('uom.uom', su, ['name', 'rounding', 'factor', 'category_id'])}
        tu.update(maps['uom.uom'][sid] for sid in su if sid in maps['uom.uom'])
        target_uoms = {x['id']:x for x in b.read('uom.uom',tu,['name','rounding','factor','relative_factor','relative_uom_id','category_id'])}
        while True:
            missing={rid(x.get('relative_uom_id')) for x in target_uoms.values() if x.get('relative_uom_id')}-set(target_uoms)
            if not missing:break
            target_uoms.update({x['id']:x for x in b.read('uom.uom',missing,['name','rounding','factor','relative_factor','relative_uom_id','category_id'])})
        result = C['compare_lines'](model, source, target, maps, source_uoms, target_uoms)
        for conflict in conflicts:
            for row in result['rows']:
                if conflict['model'] == model and conflict['source_id'] == row['source_line']:
                    row['issues'].append('conflicting_external_id'); row['match'] = False
        result['summary']['matched'] = sum(x['match'] for x in result['rows'])
        result['summary']['mismatched'] = sum(not x['match'] for x in result['rows'])
        report['models'].append(result)
        # Include every linked invoice/stock event as evidence, never migrate it here.
        inv_lines = a.read('account.move.line', [i for x in source for i in x.get('invoice_lines', [])], ['move_id', 'quantity', 'product_id', 'product_uom_id', 'sale_line_ids', 'purchase_line_id'])
        inv_headers = a.read('account.move', [rid(x['move_id']) for x in inv_lines], ['name', 'state', 'move_type', 'invoice_date', 'date', 'create_date', 'write_date'])
        stock = []
        ids = sorted(line_ids)
        for start in range(0, len(ids), 300):
            stock.extend(a.scan('stock.move', [['company_id', '=', 1], [link, 'in', ids[start:start+300]]], ['name', 'date', 'state', link, 'product_id', 'product_uom', 'quantity_done', 'product_uom_qty', 'picking_id', 'origin_returned_move_id', 'move_orig_ids', 'move_dest_ids', 'create_date', 'write_date']))
        report['dependencies'][model] = {'invoice_lines': inv_lines, 'invoices': inv_headers, 'moves': stock,
            'outside_frozen_snapshot_invoice_ids':[x['id'] for x in inv_headers if x['id'] not in frozen_invoice_ids],
            'outside_frozen_snapshot_move_ids':[x['id'] for x in stock if x['id'] not in frozen_move_ids],
            'outside_period_invoice_ids': [x['id'] for x in inv_headers if x.get('invoice_date') and not ('2026-08-01' <= x['invoice_date'] <= scope['end_utc_exclusive'][:10])],
            'outside_period_move_ids': [x['id'] for x in stock if not (scope['start_utc'] <= x['date'] < scope['end_utc_exclusive'])]}
        (evidence / ('verify-source-' + model + '.json')).write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding='utf8')
        (evidence / ('verify-target-' + model + '.json')).write_text(json.dumps(target, ensure_ascii=False, indent=2), encoding='utf8')
        print(model, result['summary'], flush=True)
    report['completed_utc']=datetime.now(timezone.utc).isoformat()
    report['passed'] = not conflicts and all(x['summary']['mismatched'] == 0 for x in report['models'])
    path = evidence / 'order-quantity-verification.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.evidence_dir))
