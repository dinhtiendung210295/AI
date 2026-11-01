"""Confirm PYSB July POs on staging only; default is read-only preflight.

Writes require a user backup acknowledgement. Supplier creation risks block
the full batch; a safe single-PO trial can still be inspected independently.
No retries of mutating RPC calls, receipt validation, or bill creation.
"""
import argparse
import copy
import json
import runpy
import socket
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[6]
Reader = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']
ORDER = ['id', 'name', 'company_id', 'partner_id', 'partner_ref', 'currency_id',
         'payment_term_id', 'picking_type_id', 'date_order', 'date_approve',
         'date_planned', 'order_line', 'state', 'amount_untaxed', 'amount_tax',
         'amount_total', 'picking_ids', 'invoice_ids', 'write_date',
         'x_studio_v14_reference_studio']
LINE = ['id', 'order_id', 'sequence', 'display_type', 'product_id', 'name',
        'product_qty', 'product_uom_id', 'price_unit', 'discount', 'tax_ids',
        'date_planned', 'price_subtotal', 'price_total', 'analytic_distribution']
PICK = ['id', 'name', 'state', 'company_id', 'picking_type_id', 'location_id',
        'location_dest_id', 'origin', 'scheduled_date', 'date_done', 'move_ids']
MOVE = ['id', 'state', 'picking_id', 'purchase_line_id', 'product_id',
        'product_uom', 'product_uom_qty', 'quantity', 'location_id',
        'location_dest_id', 'move_orig_ids', 'move_dest_ids']


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def rid(value):
    return value[0] if isinstance(value, list) and value else value or False


def same(a, b, tolerance=0.000001):
    if type(a) in (int, float) and type(b) in (int, float):
        return abs(a - b) <= tolerance
    return a == b


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def indexed(records):
    return {r['id']: r for r in records}


def external(reader, model):
    prefix = model.replace('.', '_') + '_'
    records = reader.search_read('ir.model.data', [['module', '=', 'pysb_v14'],
                                ['model', '=', model]], ['name', 'res_id'])
    result = {}
    for row in records:
        if row['name'].startswith(prefix):
            source_id = int(row['name'][len(prefix):])
            require(source_id not in result, 'Duplicate External ID')
            result[source_id] = row['res_id']
    require(len(set(result.values())) == len(result), 'Aliased External IDs: ' + model)
    return result


def import_evidence():
    path = ROOT / 'Ref/PYSB_JULY_2026_SO_PO/PYSB_PO_JULY_2026_IMPORT_01.xlsx'
    book = load_workbook(path, read_only=True, data_only=True)
    rows = iter(book.active.values)
    headers = next(rows)
    orders, lines = {}, {}
    for values in rows:
        row = dict(zip(headers, values))
        if row['ID']:
            orders[int(row['ID'].rsplit('_', 1)[1])] = row
        if row['Order Lines/ID']:
            lines[int(row['Order Lines/ID'].rsplit('_', 1)[1])] = row
    book.close()
    return orders, lines


def stored_snapshot(reader, model, ids):
    meta = reader.call(model, 'fields_get', [], {'attributes': ['type', 'store']})
    fields = [k for k, v in meta.items() if v.get('store') and
              v['type'] not in ['binary', 'one2many'] and
              not k.startswith(('message_', 'activity_'))]
    return {'fields': sorted(fields), 'records': reader.read(model, ids, sorted(fields))}


def side_effect_snapshot(reader, product_ids):
    model_names = reader.search_read('ir.model', [['model', 'in', ['stock.valuation.layer']]], ['model'])
    result = {
        'account_move_ids': reader.call('account.move', 'search', [[['company_id', '=', 1]]]),
        'quants': reader.search_read('stock.quant', [['company_id', '=', 1], ['product_id', 'in', product_ids]],
                                    ['product_id', 'location_id', 'lot_id', 'package_id', 'owner_id', 'quantity', 'reserved_quantity']),
        'cost': reader.read('product.product', product_ids, ['standard_price']),
    }
    if model_names:
        result['valuation_ids'] = reader.call('stock.valuation.layer', 'search', [[['company_id', '=', 1]]])
    return result


def verify_side_effects(reader, baseline, product_ids):
    current = side_effect_snapshot(reader, product_ids)
    require(current['account_move_ids'] == baseline['account_move_ids'], 'Accounting entries created/deleted')
    require(current.get('valuation_ids') == baseline.get('valuation_ids'), 'Valuation layers created/deleted')
    require(current['cost'] == baseline['cost'], 'Product cost changed')
    quantity = lambda data: {r['id']: {k: v for k, v in r.items() if k != 'reserved_quantity'} for r in data}
    require(quantity(current['quants']) == quantity(baseline['quants']), 'Inventory quantity changed')
    return current


def master_snapshot(reader, orders, lines):
    products = reader.read('product.product', [rid(r['product_id']) for r in lines if r['product_id']],
                           ['product_tmpl_id', 'seller_ids', 'type', 'name'])
    partners = reader.read('res.partner', [rid(r['partner_id']) for r in orders], ['parent_id'])
    partner_ids = [r['id'] for r in partners] + [rid(r['parent_id']) for r in partners if r['parent_id']]
    templates = sorted({rid(r['product_tmpl_id']) for r in products})
    snapshots = {
        'res.partner': stored_snapshot(reader, 'res.partner', partner_ids),
        'product.product': stored_snapshot(reader, 'product.product', [r['id'] for r in products]),
        'product.template': stored_snapshot(reader, 'product.template', templates),
        'product.supplierinfo': stored_snapshot(reader, 'product.supplierinfo',
                                               [i for r in products for i in r['seller_ids']]),
    }
    snapshots['supplier_ids'] = reader.call('product.supplierinfo', 'search',
                                            [[['product_tmpl_id', 'in', templates]]])
    snapshots['settings'] = reader.read('res.company', [1],
                                        ['name', 'po_double_validation', 'po_double_validation_amount', 'po_lock'])
    for model in ['stock.picking.type', 'stock.warehouse', 'stock.rule', 'stock.route', 'stock.location']:
        rows = reader.search_read(model, [], ['id'])
        snapshots[model] = stored_snapshot(reader, model, [r['id'] for r in rows])
    return snapshots, indexed(products), indexed(partners)


def verify_master(reader, baseline, additions=None):
    additions = additions or []
    touched_templates = {rid(r['product_tmpl_id']) for r in additions}
    touched_variants = {r['id'] for r in baseline['product.product']['records']
                        if rid(r['product_tmpl_id']) in touched_templates}
    for model, snapshot in baseline.items():
        if isinstance(snapshot, dict) and 'fields' in snapshot:
            current = reader.read(model, [r['id'] for r in snapshot['records']], snapshot['fields'])
            for old, new in zip(snapshot['records'], current):
                touched = (model == 'product.template' and old['id'] in touched_templates) or (model == 'product.product' and old['id'] in touched_variants)
                ignored = {'write_date', 'write_uid'} if touched else set()
                require({k: v for k, v in old.items() if k not in ignored} ==
                        {k: v for k, v in new.items() if k not in ignored}, 'Master data changed: ' + model)
            require(len(current) == len(snapshot['records']), 'Master records deleted: ' + model)
    templates = [r['id'] for r in baseline['product.template']['records']]
    require(set(reader.call('product.supplierinfo', 'search', [[['product_tmpl_id', 'in', templates]]])) ==
            set(baseline['supplier_ids']) | {r['id'] for r in additions}, 'Unreviewed supplier rows created/deleted')
    if additions:
        fields = list(additions[0])
        require(reader.read('product.supplierinfo', [r['id'] for r in additions], fields) == additions,
                'Approved new supplier rows changed')
    require(reader.read('res.company', [1], ['name', 'po_double_validation',
            'po_double_validation_amount', 'po_lock']) == baseline['settings'], 'Company settings changed')


def capture_supplier_additions(reader, group, baseline, previous):
    templates = [r['id'] for r in baseline['product.template']['records']]
    ids = set(reader.call('product.supplierinfo', 'search', [[['product_tmpl_id', 'in', templates]]]))
    new_ids = ids - set(baseline['supplier_ids']) - {r['id'] for r in previous}
    products = indexed(reader.read('product.product', group['supplier_risk'], ['product_tmpl_id', 'uom_id']))
    partner = reader.read('res.partner', [rid(group['before']['partner_id'])], ['parent_id'])[0]
    vendor = rid(partner['parent_id']) or partner['id']
    expected = {}
    for line in group['lines']:
        pid = rid(line['product_id'])
        if pid not in products:
            continue
        product = products[pid]
        units = indexed(reader.read('uom.uom', [rid(product['uom_id']), rid(line['product_uom_id'])], ['factor']))
        price = line['price_unit'] * units[rid(product['uom_id'])]['factor'] / units[rid(line['product_uom_id'])]['factor']
        expected.setdefault((rid(product['product_tmpl_id']), vendor), (price, line['discount']))
    rows = stored_snapshot(reader, 'product.supplierinfo', sorted(new_ids))['records']
    seen = set()
    for row in rows:
        key = (rid(row['product_tmpl_id']), rid(row['partner_id']))
        require(key in expected and key not in seen, 'Unapproved/duplicate supplier link')
        seen.add(key)
        price, discount = expected[key]
        require(not row['product_id'] and rid(row['currency_id']) == rid(group['before']['currency_id']), 'New supplier scope/currency mismatch')
        require(same(row['price'], price) and same(row['discount'], discount) and row['min_qty'] == 1 and row['delay'] == 0,
                'New supplier commercial values mismatch')
    require(seen == set(expected), 'Expected supplier links were not created')
    return previous + rows


def workflow_snapshot(reader, order):
    pickings = reader.read('stock.picking', order['picking_ids'], PICK)
    # Include purchase-linked moves and downstream moves for chained routes.
    moves = reader.search_read('stock.move', [['purchase_line_id', 'in', order['order_line']]], MOVE)
    seen = {r['id'] for r in moves}
    pending = {i for r in moves for i in r['move_dest_ids']} - seen
    while pending:
        extra = reader.read('stock.move', sorted(pending), MOVE)
        moves += extra
        seen.update(r['id'] for r in extra)
        pending = {i for r in extra for i in r['move_dest_ids']} - seen
    extra_picks = {rid(r['picking_id']) for r in moves if r['picking_id']} - {r['id'] for r in pickings}
    pickings += reader.read('stock.picking', sorted(extra_picks), PICK)
    return {'pickings': pickings, 'moves': sorted(moves, key=lambda r: r['id'])}


def preflight(a, b):
    source = a.search_read('purchase.order', [['company_id', '=', 1], ['date_order', '>=', '2026-07-01'],
                          ['date_order', '<', '2026-08-01'], ['state', 'in', ['purchase', 'done']]],
                          ['name', 'date_order', 'date_approve', 'partner_id', 'order_line',
                           'partner_ref', 'currency_id', 'amount_untaxed', 'amount_tax', 'amount_total'])
    require(len(source) == 86, 'Source scope no longer has 86 POs')
    om, lm = external(b, 'purchase.order'), external(b, 'purchase.order.line')
    require(all(s['id'] in om for s in source), 'Missing PO External IDs')
    orders = b.read('purchase.order', [om[s['id']] for s in source], ORDER)
    by_id = indexed(orders)
    require(len(orders) == 86, 'Missing target orders')
    refs = b.search_read('purchase.order', [['company_id', '=', 1],
                         ['x_studio_v14_reference_studio', 'in', [s['name'] for s in source]]], ['id'])
    require({r['id'] for r in refs} == set(by_id), 'Reference and External ID scopes disagree')
    lines = b.read('purchase.order.line', [i for r in orders for i in r['order_line']], LINE)
    target_lines = indexed(lines)
    sf = ['id', 'order_id', 'display_type', 'product_id', 'name', 'product_qty',
          'product_uom', 'price_unit', 'taxes_id', 'date_planned', 'price_subtotal']
    source_lines = indexed(a.read('purchase.order.line', [i for r in source for i in r['order_line']], sf))
    evidence_orders, evidence_lines = import_evidence()
    supplement_path = ROOT / 'outputs/pysb-so-po-20261012-staging-supplement/journal.json'
    supplement = json.loads(supplement_path.read_text(encoding='utf-8'))
    master, products, partners = master_snapshot(b, orders, lines)
    suppliers = indexed(master['product.supplierinfo']['records'])
    modules = b.search_read('ir.module.module', [['state', '=', 'installed']], ['name', 'installed_version'])
    automations = b.search_read('base.automation', [['active', '=', True]],
                               ['name', 'model_id', 'trigger', 'action_server_ids', 'filter_domain', 'filter_pre_domain'])
    actions = b.read('ir.actions.server', [i for r in automations for i in r['action_server_ids']],
                     ['name', 'model_id', 'state', 'code'])
    relevant = b.search_read('ir.model', [['model', 'in', ['purchase.order', 'purchase.order.line',
                             'stock.move', 'stock.picking', 'product.template', 'product.product']]], ['model'])
    relevant_ids = {r['id'] for r in relevant}
    auto_risk = [r['name'] for r in automations if rid(r['model_id']) in relevant_ids and r['trigger'] != 'on_change']
    groups = []
    for s in source:
        t = by_id[om[s['id']]]
        issues = []
        def check(ok, message):
            if not ok: issues.append(message)
        check(rid(t['company_id']) == 1 and t['x_studio_v14_reference_studio'] == s['name'], 'PO identity/company mismatch')
        check(t['state'] in ['draft', 'sent', 'purchase'], 'Unexpected PO state')
        check(bool(s['date_approve']), 'Missing historical approval date')
        check(not t['invoice_ids'], 'PO already has bills')
        check(t['state'] == 'purchase' or not t['picking_ids'], 'Unconfirmed PO already has pickings')
        ev = evidence_orders.get(s['id'])
        check(bool(ev) and rid(t['partner_id']) == ev['Vendor/Database ID'], 'Vendor mapping differs from import evidence')
        check(t['partner_ref'] == s['partner_ref'], 'Vendor reference mismatch')
        # Bruce explicitly confirmed this cleaned-v19 currency mapping on 2026-10-12.
        currency_name = {'CNH': 'CNY'}.get(s['currency_id'][1], s['currency_id'][1])
        check(t['currency_id'][1] == currency_name, 'Currency mismatch')
        for k in ['amount_untaxed', 'amount_tax', 'amount_total']:
            check(same(s[k], t[k], 0.01), 'Amount mismatch: ' + k)
        mapped = [lm.get(i) for i in s['order_line']]
        check(None not in mapped and set(mapped) == set(t['order_line']), 'Missing/extra/mislinked lines')
        for sid in s['order_line']:
            sl, tl = source_lines[sid], target_lines.get(lm.get(sid))
            if not tl: continue
            check(rid(tl['order_id']) == t['id'], 'Line belongs to another PO')
            for k in ['display_type', 'name', 'product_qty', 'price_unit', 'price_subtotal']:
                check(same(sl[k], tl[k]), f'Line {sid}: {k} mismatch')
            check(bool(sl['taxes_id']) == bool(tl['tax_ids']), f'Line {sid}: source/target tax presence mismatch')
            iev = evidence_lines.get(sid)
            if iev:
                check(rid(tl['product_id']) == (iev['Order Lines/Product/Database ID'] or False), f'Line {sid}: product mapping mismatch')
                check(rid(tl['product_uom_id']) == (iev['Order Lines/Unit/Database ID'] or False), f'Line {sid}: UOM mapping mismatch')
                expected_tax = sorted(int(x) for x in str(iev['Order Lines/Taxes/Database ID'] or '').split(',') if x)
                check(sorted(tl['tax_ids']) == expected_tax, f'Line {sid}: tax mapping mismatch')
            else:
                entry = supplement.get(str(sid))
                check(bool(entry) and entry.get('status') == 'linked' and entry['target_line_id'] == tl['id'],
                      f'Line {sid}: no verified supplement journal mapping')
                if entry:
                    values = entry['values']
                    check(rid(sl['order_id']) == s['id'] and values['order_id'] == t['id'], 'Supplement order relation mismatch')
                    for field in ['product_id', 'product_uom_id']:
                        check(rid(tl[field]) == values[field], f'Line {sid}: supplement {field} mapping mismatch')
                    check(tl['tax_ids'] == values['tax_ids'][0][2], f'Line {sid}: supplement taxes mismatch')
        risk = []
        partner = partners[rid(t['partner_id'])]
        vendor_ids = {partner['id'], rid(partner['parent_id'])}
        for lid in t['order_line']:
            line = target_lines[lid]
            if not line['product_id']: continue
            p = products[rid(line['product_id'])]
            if len(p['seller_ids']) <= 10 and not vendor_ids.intersection(rid(suppliers[i]['partner_id']) for i in p['seller_ids']):
                risk.append(p['id'])
        groups.append({'source': s, 'before': t, 'lines': [target_lines[i] for i in t['order_line']],
                       'workflow_before': workflow_snapshot(b, t), 'issues': issues,
                       'supplier_risk': sorted(set(risk)) if t['state'] != 'purchase' else [],
                       'has_stock_goods': any(products[rid(target_lines[i]['product_id'])]['type'] == 'consu'
                                             for i in t['order_line'] if target_lines[i]['product_id'])})
    return {'groups': groups, 'source_lines': list(source_lines.values()), 'master': master,
            'modules': modules, 'automations': automations, 'server_actions': actions,
            'automation_risks': auto_risk,
            'states': dict(Counter(t['state'] for t in orders)),
            'side_effects_before': side_effect_snapshot(b, sorted(products))}


def normalized_move_quantity(reader, move, line):
    if rid(move['product_uom']) == rid(line['product_uom_id']):
        return move['product_uom_qty']
    units = indexed(reader.read('uom.uom', [rid(move['product_uom']), rid(line['product_uom_id'])],
                                ['factor', 'relative_uom_id', 'rounding']))
    origin, destination = units[rid(move['product_uom'])], units[rid(line['product_uom_id'])]
    require(origin['factor'] > 0 and destination['factor'] > 0, 'Invalid UOM conversion factor')
    return move['product_uom_qty'] * origin['factor'] / destination['factor']


def verify_order(b, group, products):
    before = group['before']
    after = b.read('purchase.order', [before['id']], ORDER)[0]
    require(after['state'] == 'purchase', 'PO not confirmed')
    require(after['date_approve'] == group['source']['date_approve'], 'Historical date not restored')
    for key in ORDER:
        if key not in ['state', 'date_approve', 'picking_ids', 'write_date']:
            require(before[key] == after[key], 'Order field changed: ' + key)
    current_lines = b.read('purchase.order.line', before['order_line'], LINE)
    require(current_lines == group['lines'], 'Commercial line values changed')
    workflow = workflow_snapshot(b, after)
    require(all(p['state'] != 'done' and not p['date_done'] for p in workflow['pickings']), 'Receipt unexpectedly completed')
    require(all(m['state'] != 'done' for m in workflow['moves']), 'Stock movement unexpectedly completed')
    direct = [m for m in workflow['moves'] if rid(m['purchase_line_id']) in before['order_line'] and m['state'] != 'cancel']
    for line in group['lines']:
        moves = [m for m in direct if rid(m['purchase_line_id']) == line['id']]
        stock_line = line['product_id'] and products[rid(line['product_id'])]['type'] == 'consu' and line['product_qty'] > 0
        if stock_line:
            require(bool(moves), 'Missing stock move for line ' + str(line['id']))
            require(len(moves) == 1, 'Multiple direct movements for line ' + str(line['id']))
        for move in moves:
            require(rid(move['product_id']) == rid(line['product_id']), 'Move product mismatch')
            require(rid(move['product_uom']) in [rid(line['product_uom_id']), rid(products[rid(line['product_id'])].get('uom_id'))],
                    'Move UOM is neither purchase nor product inventory unit')
            picking = next((p for p in workflow['pickings'] if p['id'] == rid(move['picking_id'])), None)
            require(picking is not None, 'Movement has no receipt')
            require(rid(picking['company_id']) == 1 and rid(picking['picking_type_id']) == rid(before['picking_type_id']), 'Receipt company/type mismatch')
            require(rid(move['location_id']) == rid(picking['location_id']), 'Receipt source location mismatch')
        if moves:
            converted = sum(normalized_move_quantity(b, m, line) for m in moves)
            require(same(converted, line['product_qty']), 'Duplicate/missing movement quantity after UOM conversion')
    if group['has_stock_goods']:
        require(bool(workflow['pickings']) and bool(direct), 'Stock PO has no receipt/moves')
    return {'order': after, 'lines': current_lines, 'workflow': workflow}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['preflight', 'sample', 'batch', 'verify'], default='preflight')
    parser.add_argument('--backup-ack', help='Exact user acknowledgement, recorded in audit')
    parser.add_argument('--allow-supplier-links', action='store_true', help='Bruce explicitly authorized adding supplier links')
    parser.add_argument('--sample-reference', help='Explicit PO for a supplier-creation trial')
    parser.add_argument('--baseline', type=Path, help='Passed sample report required for batch')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'outputs/pysb-po-confirm-20261012-staging')
    args = parser.parse_args()
    socket.setdefaulttimeout(30)
    a = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    b = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    require((a.url, a.db) == ('http://175.145.85.151', 'paoyeang_live'), 'Source environment guard failed')
    require((b.url, b.db) == ('https://py-staging.odoo.com', 'py19-staging-39654560'), 'Target environment guard failed')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = args.output_dir / f'{args.mode}-{stamp}.json'
    report = {'target_database': b.db, 'mode': args.mode, 'started_at_utc': stamp,
              'backup_ack': args.backup_ack, 'writes_attempted': False, 'writes_this_run': False, 'actions': [],
              'allow_supplier_links': args.allow_supplier_links, 'supplier_additions': []}
    try:
        if args.mode == 'verify':
            require(args.baseline is not None, 'Verification requires an original sample report')
            previous = json.loads(args.baseline.read_text(encoding='utf-8'))
            require(previous['mode'] == 'sample' and previous['target_database'] == b.db and len(previous['actions']) == 1,
                    'Only the original single-PO staging trial can be verified this way')
            report = copy.deepcopy(previous)
            report.update(execution_mode='verify', original_report=str(args.baseline), verification_at_utc=stamp,
                          original_error=report.pop('error', None), writes_this_run=False)
            action = report['actions'][0]
            group = next(g for g in report['groups'] if g['before']['id'] == action['target_id'])
            products = indexed(b.read('product.product', [r['id'] for r in report['master']['product.product']['records']], ['type', 'uom_id']))
            action['after'] = verify_order(b, group, products)
            verify_master(b, report['master'], report.get('supplier_additions', []))
            action['side_effects_after'] = verify_side_effects(b, report['side_effects_before'], sorted(products))
            action['phase'] = 'passed'
            report['last_completed_po'] = action['reference']
            report['status'] = 'passed'
            ids = [g['before']['id'] for g in report['groups']]
            report['final_states'] = dict(Counter(r['state'] for r in b.read('purchase.order', ids, ['state'])))
            save(path, report)
            print(json.dumps({'report': str(path), 'status': 'passed', 'final_states': report['final_states'],
                              'writes_this_run': False}, ensure_ascii=False))
            return 0
        report.update(preflight(a, b))
        save(path, report)
        eligible = [g for g in report['groups'] if not g['issues'] and (not g['supplier_risk'] or args.allow_supplier_links) and
                    g['before']['state'] == 'draft' and (g['has_stock_goods'] or args.sample_reference)]
        if args.sample_reference:
            eligible = [g for g in eligible if g['source']['name'] == args.sample_reference]
        report['sample_candidate'] = min(eligible, key=lambda g: g['source']['id'])['source']['name'] if eligible else None
        if args.mode == 'preflight':
            report['status'] = 'read_only_preflight'
        else:
            require(args.backup_ack, 'User backup acknowledgement is required')
            require(not report['automation_risks'], 'Relevant automation needs review')
            require(report['master']['settings'][0]['po_double_validation'] == 'one_step', 'Approval configuration changed')
            if args.mode == 'sample':
                require(bool(eligible), 'No safe sample PO')
                selected = [min(eligible, key=lambda g: g['source']['id'])]
            else:
                require(args.baseline is not None, 'A passed sample report is required')
                previous = json.loads(args.baseline.read_text(encoding='utf-8'))
                require(previous['mode'] == 'sample' and previous.get('status') == 'passed' and
                        previous['target_database'] == b.db, 'Sample report is not passed staging evidence')
                verify_master(b, previous['master'], previous.get('supplier_additions', []))
                require([g['source'] for g in report['groups']] == [g['source'] for g in previous['groups']], 'Source changed since sample')
                require(report['source_lines'] == previous['source_lines'], 'Source lines changed since sample')
                require(not any(g['issues'] or (g['supplier_risk'] and not args.allow_supplier_links) for g in report['groups']),
                        'Batch blocked by preflight or supplier preservation exceptions')
                selected = sorted(report['groups'], key=lambda g: g['source']['id'])
            for g in selected:
                before = g['before']
                verify_master(b, report['master'], report['supplier_additions'])
                require(b.read('purchase.order', [before['id']], ORDER)[0] == before, 'PO changed since preflight')
                require(b.read('purchase.order.line', before['order_line'], LINE) == g['lines'], 'Lines changed since preflight')
                require(workflow_snapshot(b, before) == g['workflow_before'], 'Workflow changed since preflight')
                action = {'reference': g['source']['name'], 'target_id': before['id'], 'phase': 'before_confirm'}
                report['actions'].append(action)
                report['writes_attempted'] = True
                report['writes_this_run'] = True
                save(path, report)
                if before['state'] in ['draft', 'sent']:
                    # Never retry this call automatically if the response is lost.
                    b.call('purchase.order', 'button_confirm', [[before['id']]],
                           {'context': {'tracking_disable': True, 'mail_auto_subscribe_no_notify': True}})
                    action['phase'] = 'confirmed_pending_date_restore'
                    if args.allow_supplier_links:
                        report['supplier_additions'] = capture_supplier_additions(b, g, report['master'], report['supplier_additions'])
                    save(path, report)
                if before['date_approve'] != g['source']['date_approve'] or before['state'] != 'purchase':
                    b.call('purchase.order', 'write', [[before['id']], {'date_approve': g['source']['date_approve']}])
                action['phase'] = 'verify'
                save(path, report)
                products = indexed(b.read('product.product', [r['id'] for r in report['master']['product.product']['records']], ['type', 'uom_id']))
                action['after'] = verify_order(b, g, products)
                verify_master(b, report['master'], report['supplier_additions'])
                action['side_effects_after'] = verify_side_effects(b, report['side_effects_before'], sorted(products))
                action['phase'] = 'passed'
                report['last_completed_po'] = g['source']['name']
                save(path, report)
                print(json.dumps({'reference': g['source']['name'], 'status': 'passed'}, ensure_ascii=False), flush=True)
            report['status'] = 'passed'
            ids = [g['before']['id'] for g in report['groups']]
            report['final_states'] = dict(Counter(r['state'] for r in b.read('purchase.order', ids, ['state'])))
    except Exception as exc:
        report['status'] = 'stopped'
        report['error'] = str(exc)
        if report['actions']:
            last = report['actions'][-1]
            try:
                current = b.read('purchase.order', [last['target_id']], ORDER)[0]
                last['recovery_read'] = {'order': current, 'workflow': workflow_snapshot(b, current)}
            except Exception as read_error:
                last['recovery_read_error'] = str(read_error)
    finally:
        save(path, report)
    print(json.dumps({'report': str(path), 'status': report['status'], 'error': report.get('error'),
                      'states': report.get('states'), 'sample_candidate': report.get('sample_candidate'),
                      'supplier_risk_pos': sum(bool(g['supplier_risk']) for g in report.get('groups', [])),
                      'exception_pos': sum(bool(g['issues']) for g in report.get('groups', [])),
                      'writes_attempted': report['writes_attempted']}, ensure_ascii=False))
    return 0 if report['status'] != 'stopped' else 1


if __name__ == '__main__':
    raise SystemExit(main())
