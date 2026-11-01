"""Scoped XML-RPC supplement: four known service lines, staging only."""
import argparse
import json
import runpy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
Reader = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']
PLAN = [(19755, 5195, 'PO-04439', 520, 54407, 118222),
        (20184, 5216, 'PO-04449', 529, 47038, 114946),
        (20185, 5216, 'PO-04449', 529, 47038, 114946),
        (19748, 5225, 'PO-04456', 535, 54407, 118222)]
SOURCE_FIELDS = ['id', 'order_id', 'product_id', 'name', 'product_qty', 'product_uom', 'price_unit', 'taxes_id', 'date_planned', 'sequence', 'display_type', 'price_subtotal', 'price_total']
LINE_FIELDS = ['id', 'order_id', 'product_id', 'name', 'product_qty', 'product_uom_id', 'price_unit', 'discount', 'tax_ids', 'date_planned', 'sequence', 'display_type', 'price_subtotal', 'price_total', 'write_date']
ORDER_FIELDS = ['id', 'name', 'company_id', 'partner_id', 'state', 'currency_id', 'order_line', 'amount_untaxed', 'amount_tax', 'amount_total', 'picking_ids', 'invoice_ids', 'x_studio_v14_reference_studio', 'x_studio_date_ref_v14_studio']


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def close(a, b):
    return abs(float(a) - float(b)) < 0.000001


def matching(line, values):
    return all(line[k] == values[k] for k in ['name', 'date_planned', 'sequence', 'display_type']) and all(
        line[k][0] == values[k] for k in ['order_id', 'product_id', 'product_uom_id']) and all(
        close(line[k], values[k]) for k in ['product_qty', 'price_unit', 'discount']) and line['tax_ids'] == []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int, choices=[1, 4], default=4)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    target = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    require(source.db == 'paoyeang_live' and source.url == 'http://175.145.85.151', 'Unexpected source')
    require(target.db == 'py19-staging-39654560' and target.url == 'https://py-staging.odoo.com', 'Staging guard failed')
    journal_path = args.output_dir / 'journal.json'
    journal = json.loads(journal_path.read_text(encoding='utf-8')) if journal_path.exists() else {}
    source_lines = {r['id']: r for r in source.read('purchase.order.line', [p[0] for p in PLAN], SOURCE_FIELDS)}
    source_orders = {r['id']: r for r in source.read('purchase.order', [p[1] for p in PLAN], ['id', 'name', 'company_id', 'date_order', 'order_line'])}
    orders = {r['id']: r for r in target.read('purchase.order', [p[3] for p in PLAN], ORDER_FIELDS)}
    before_lines = target.read('purchase.order.line', [i for r in orders.values() for i in r['order_line']], LINE_FIELDS)
    product_fields = ['id', 'name', 'type', 'active', 'company_id', 'uom_id', 'default_code', 'barcode', 'write_date']
    products = {r['id']: r for r in target.read('product.product', [p[5] for p in PLAN], product_fields)}
    source_products = {r['id']: r for r in source.read('product.product', [p[4] for p in PLAN], ['id', 'name', 'type', 'uom_id', 'default_code', 'barcode'])}
    partner_fields = ['id', 'name', 'write_date']
    partners = target.read('res.partner', [r['partner_id'][0] for r in orders.values()], partner_fields)
    entries = []
    for sid, soid, ref, toid, spid, tpid in PLAN:
        row, so, order = source_lines[sid], source_orders[soid], orders[toid]
        require(so['company_id'][0] == order['company_id'][0] == 1, 'Company mismatch')
        require(so['name'] == ref == order['x_studio_v14_reference_studio'], 'Reference mismatch')
        require('2026-07-01' <= so['date_order'] < '2026-08-01', 'Source date outside July')
        require(row['order_id'][0] == soid and sid in so['order_line'] and row['product_id'][0] == spid, 'Source relation mismatch')
        require(order['state'] == 'draft', 'Only draft PO supported')
        sp, tp = source_products[spid], products[tpid]
        require(sp['name'] == tp['name'] and sp['type'] == tp['type'] == 'service', 'Product mismatch')
        require(tp['active'] and tp['company_id'][0] == 1, 'Product company/active mismatch')
        candidates = target.search_read('product.product', [['name', '=', sp['name']], ['company_id', 'in', [1, False]]], ['id'])
        require([r['id'] for r in candidates] == [tpid], 'Product mapping not unique')
        require(row['product_uom'][1] == 'UNIT' and tp['uom_id'][1] == 'Units', 'UoM mismatch')
        require(not row['taxes_id'] and not row['display_type'], 'Unsupported taxes/display type')
        values = {'order_id': toid, 'product_id': tpid, 'name': row['name'], 'product_qty': row['product_qty'],
                  'product_uom_id': tp['uom_id'][0], 'price_unit': row['price_unit'], 'discount': 0.0,
                  'tax_ids': [[6, 0, []]], 'date_planned': row['date_planned'], 'sequence': row['sequence'], 'display_type': False}
        xid = f'purchase_order_line_{sid}'
        identifiers = target.search_read('ir.model.data', [['module', '=', 'pysb_v14'], ['name', '=', xid]], ['id', 'model', 'res_id'])
        require(len(identifiers) <= 1, 'Duplicate external ID')
        already = False
        if identifiers:
            ident = identifiers[0]
            require(ident['model'] == 'purchase.order.line', 'External ID wrong model')
            existing = target.read('purchase.order.line', [ident['res_id']], LINE_FIELDS)
            require(len(existing) == 1 and matching(existing[0], values), 'Existing external ID mismatch')
            already = True
        else:
            duplicates = [r for r in before_lines if matching(r, values)]
            if duplicates:
                # Recover only a line whose successful create is in our durable journal.
                known = journal.get(str(sid), {}).get('target_line_id')
                require(len(duplicates) == 1 and duplicates[0]['id'] == known, 'Unmarked matching line; manual investigation required')
        entries.append({'source_id': sid, 'reference': ref, 'external_id': xid, 'values': values, 'source': row, 'already_present': already})
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report = {'target_database': target.db, 'apply': args.apply, 'before_orders': list(orders.values()),
              'before_lines': before_lines, 'before_products': list(products.values()), 'before_partners': partners,
              'plan': entries, 'actions': []}
    report_path = args.output_dir / f'run-{stamp}.json'
    save(report_path, report)
    if args.apply:
        for entry in entries[:args.limit]:
            sid, values = entry['source_id'], entry['values']
            if entry['already_present']:
                report['actions'].append({'source_id': sid, 'action': 'skip_existing'})
                continue
            current = target.read('purchase.order', [values['order_id']], ORDER_FIELDS)[0]
            expected = orders[values['order_id']]
            require(current == expected, 'PO changed since preflight; stop')
            known = journal.get(str(sid), {}).get('target_line_id')
            if known:
                created = target.read('purchase.order.line', [known], LINE_FIELDS)
                require(len(created) == 1 and matching(created[0], values), 'Recovery journal mismatch')
                line_id = known
            else:
                # Intent persisted before create; transport uncertainty never triggers automatic retry.
                require(str(sid) not in journal, 'Earlier create outcome uncertain; investigate before retry')
                journal[str(sid)] = {'status': 'create_requested', 'values': values}
                save(journal_path, journal)
                line_id = target.call('purchase.order.line', 'create', [values], {'context': {'tracking_disable': True, 'mail_create_nosubscribe': True}})
                journal[str(sid)].update(target_line_id=line_id, status='created')
                save(journal_path, journal)
            ident_id = target.call('ir.model.data', 'create', [{'module': 'pysb_v14', 'name': entry['external_id'], 'model': 'purchase.order.line', 'res_id': line_id, 'noupdate': True}])
            journal[str(sid)].update(external_id_record=ident_id, status='linked')
            save(journal_path, journal)
            actual = target.read('purchase.order.line', [line_id], LINE_FIELDS)[0]
            require(matching(actual, values), 'New line verification failed')
            require(close(actual['price_subtotal'], entry['source']['price_subtotal']) and close(actual['price_total'], entry['source']['price_total']), 'New line amount mismatch')
            report['actions'].append({'source_id': sid, 'target_line_id': line_id, 'action': 'created_and_verified'})
            orders[values['order_id']] = target.read('purchase.order', [values['order_id']], ORDER_FIELDS)[0]
            save(report_path, report)
        after_orders = target.read('purchase.order', list(orders), ORDER_FIELDS)
        old_now = target.read('purchase.order.line', [r['id'] for r in before_lines], LINE_FIELDS)
        require(old_now == before_lines, 'Pre-existing lines changed')
        require(target.read('product.product', list(products), product_fields) == list(products.values()), 'Products changed')
        require(target.read('res.partner', [r['id'] for r in partners], partner_fields) == partners, 'Partners changed')
        immutable = ['id', 'name', 'company_id', 'partner_id', 'state', 'currency_id', 'picking_ids', 'invoice_ids', 'x_studio_v14_reference_studio', 'x_studio_date_ref_v14_studio']
        for order in after_orders:
            before = next(o for o in report['before_orders'] if o['id'] == order['id'])
            require(all(before[k] == order[k] for k in immutable), 'PO identity/state/related documents changed')
            additions = [e for e in entries if any(a.get('source_id') == e['source_id'] and a['action'] == 'created_and_verified' for a in report['actions']) and e['values']['order_id'] == order['id'] and journal[str(e['source_id'])]['target_line_id'] not in before['order_line']]
            added_ids = [journal[str(e['source_id'])]['target_line_id'] for e in additions]
            require(set(order['order_line']) == set(before['order_line'] + added_ids), 'Unexpected order lines')
            for key in ['amount_untaxed', 'amount_total']:
                require(close(order[key], before[key] + sum(e['source']['price_subtotal'] for e in additions)), 'Unexpected PO total delta')
            require(close(order['amount_tax'], before['amount_tax']), 'PO tax changed')
        report.update(after_orders=after_orders, verification='passed')
        save(report_path, report)
    print(json.dumps({'report': str(report_path), 'missing': sum(not e['already_present'] for e in entries), 'actions': report['actions'], 'verification': report.get('verification', 'read_only_preflight')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
