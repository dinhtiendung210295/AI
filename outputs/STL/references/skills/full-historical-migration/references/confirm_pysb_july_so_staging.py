"""Staging-only SO confirmation in batches; no inventory/accounting audit."""
import argparse
import json
import runpy
import socket
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[6]
helpers = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
Reader, require, save, external, rid = [helpers[k] for k in ['Reader', 'require', 'save', 'external', 'rid']]
ORDER = ['id', 'name', 'state', 'date_order', 'company_id', 'partner_id', 'partner_invoice_id',
         'partner_shipping_id', 'currency_id', 'pricelist_id', 'payment_term_id', 'warehouse_id',
         'commitment_date', 'client_order_ref', 'note', 'order_line', 'amount_untaxed', 'amount_tax',
         'amount_total', 'picking_ids', 'invoice_ids', 'x_studio_v14_reference_studio', 'woo_order_id']
LINE = ['id', 'order_id', 'sequence', 'display_type', 'product_id', 'name', 'product_uom_qty',
        'product_uom_id', 'price_unit', 'discount', 'base_price', 'is_free', 'tax_ids',
        'route_ids', 'customer_lead', 'price_subtotal', 'price_total', 'analytic_distribution']


def evidence():
    orders, lines = {}, {}
    for path in sorted((ROOT / 'Ref/PYSB_JULY_2026_SO_PO').glob('PYSB_SO_JULY_2026_IMPORT_*.xlsx')):
        book = load_workbook(path, read_only=True, data_only=True)
        rows = iter(book.active.values)
        header = next(rows)
        for values in rows:
            row = dict(zip(header, values))
            if row['ID']:
                orders[int(row['ID'].rsplit('_', 1)[1])] = row
            if row['Order Lines/ID']:
                lines[int(row['Order Lines/ID'].rsplit('_', 1)[1])] = row
        book.close()
    return orders, lines


def masters(reader, orders, lines):
    products = reader.read('product.product', [rid(r['product_id']) for r in lines if r['product_id']], ['product_tmpl_id', 'type'])
    ids = {model: values for model, values in [
        ('res.partner', [rid(r[k]) for r in orders for k in ['partner_id', 'partner_invoice_id', 'partner_shipping_id'] if r[k]]),
        ('product.product', [r['id'] for r in products]),
        ('product.template', [rid(r['product_tmpl_id']) for r in products]),
    ]}
    # One snapshot before and one after the run, not after every SO.
    return {model: helpers['stored_snapshot'](reader, model, values) for model, values in ids.items()}


def verify_masters(reader, baseline):
    for model, data in baseline.items():
        require(reader.read(model, [r['id'] for r in data['records']], data['fields']) == data['records'],
                'Master data changed: ' + model)


def preflight(source, target):
    domain = [['company_id', '=', 1], ['date_order', '>=', '2026-07-01'], ['date_order', '<', '2026-08-01'],
              ['state', 'in', ['sale', 'done']], ['is_quotation_template', '=', False]]
    sf = ['name', 'date_order', 'order_line', 'partner_id', 'amount_untaxed', 'amount_tax', 'amount_total']
    sources = source.search_read('sale.order', domain, sf)
    require(len(sources) == 953, 'Source scope no longer has 953 SOs')
    om, lm = external(target, 'sale.order'), external(target, 'sale.order.line')
    require(all(r['id'] in om for r in sources), 'Missing SO External ID')
    orders = target.read('sale.order', [om[r['id']] for r in sources], ORDER)
    td = {r['id']: r for r in orders}
    refs = target.search_read('sale.order', [['company_id', '=', 1],
         ['x_studio_v14_reference_studio', 'in', [r['name'] for r in sources]]], ['id'])
    require({r['id'] for r in refs} == set(td), 'Reference and External ID scopes differ')
    lines = target.read('sale.order.line', [i for r in orders for i in r['order_line']], LINE)
    tl = {r['id']: r for r in lines}
    sfields = ['order_id', 'display_type', 'product_id', 'name', 'product_uom_qty', 'price_unit',
               'discount', 'base_price', 'is_free', 'price_subtotal', 'tax_id']
    sl = {r['id']: r for r in source.read('sale.order.line', [i for r in sources for i in r['order_line']], sfields)}
    eo, el = evidence()
    products = {r['id']: r for r in target.read('product.product', [rid(r['product_id']) for r in lines if r['product_id']],
                                             ['type', 'service_tracking'])}
    require(all(r['service_tracking'] == 'no' for r in products.values()), 'Service project/task creation needs separate review')
    groups = []
    for s in sources:
        t = td[om[s['id']]]
        issues = []
        def check(ok, text):
            if not ok:
                issues.append(text)
        check(rid(t['company_id']) == 1 and t['x_studio_v14_reference_studio'] == s['name'], 'SO identity/company mismatch')
        check(t['state'] in ['draft', 'sent', 'sale'], 'Unexpected SO state')
        check(not t['invoice_ids'], 'SO already has invoices')
        check(t['state'] == 'sale' or not t['picking_ids'], 'Unconfirmed SO already has pickings')
        order_evidence = eo.get(s['id'])
        check(bool(order_evidence), 'Missing original import evidence')
        if order_evidence:
            check(rid(t['partner_id']) == order_evidence['Customer/Database ID'], 'Customer mapping mismatch')
            check(rid(t['warehouse_id']) == order_evidence['Warehouse/Database ID'], 'Warehouse mapping mismatch')
        for key in ['amount_untaxed', 'amount_tax', 'amount_total']:
            check(abs(s[key] - t[key]) <= 0.01, 'Amount mismatch: ' + key)
        check({lm.get(i) for i in s['order_line']} == set(t['order_line']), 'Missing/extra SO lines')
        for sid in s['order_line']:
            st, tt = sl[sid], tl.get(lm.get(sid))
            if not tt:
                continue
            check(rid(tt['order_id']) == t['id'], 'Line belongs to another SO')
            for key in ['display_type', 'name', 'product_uom_qty', 'price_unit', 'discount', 'base_price', 'is_free', 'price_subtotal']:
                check(helpers['same'](st[key], tt[key]), f'Line {sid}: {key} differs from source')
            item = el.get(sid)
            check(bool(item), f'Line {sid}: missing import evidence')
            if item:
                check(rid(tt['product_id']) == (item['Order Lines/Product/Database ID'] or False), f'Line {sid}: product mapping mismatch')
                check(rid(tt['product_uom_id']) == (item['Order Lines/Unit/Database ID'] or False), f'Line {sid}: UOM mapping mismatch')
            if tt['product_id'] and not tt['display_type'] and tt['base_price'] <= 0 and not tt['is_free'] and products[rid(tt['product_id'])]['type'] != 'service' and not t['woo_order_id']:
                check(False, f'Line {sid}: Base Price is zero, not a free item, no Woo order')
        groups.append({'source': s, 'before': t, 'lines': [tl[i] for i in t['order_line']], 'issues': issues})
    return {'groups': groups, 'source_lines': list(sl.values()), 'master_before': masters(target, orders, lines),
            'initial_states': dict(Counter(r['state'] for r in orders))}


def verify_group(reader, groups):
    current = {r['id']: r for r in reader.read('sale.order', [g['before']['id'] for g in groups], ORDER)}
    all_lines = [line for g in groups for line in g['lines']]
    require(reader.read('sale.order.line', [r['id'] for r in all_lines], LINE) == all_lines, 'Commercial lines changed')
    for g in groups:
        old, new = g['before'], current[g['before']['id']]
        require(new['state'] == 'sale', 'SO is not confirmed')
        require(new['date_order'] == g['source']['date_order'], 'Historical SO date differs from v14')
        for key in ORDER:
            if key not in ['state', 'date_order', 'picking_ids']:
                require(old[key] == new[key], 'SO field changed: ' + key)
    return list(current.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['preflight', 'sample', 'batch'], default='preflight')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--batch-size', type=int, default=25)
    parser.add_argument('--confirm-one-by-one', action='store_true', help='Work around deployed paoyeang_sale.write singleton bug; verify by batch')
    args = parser.parse_args()
    require(1 <= args.batch_size <= 50, 'Invalid batch size')
    socket.setdefaulttimeout(60)
    a = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    b = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    require((a.url, a.db) == ('http://175.145.85.151', 'paoyeang_live'), 'Wrong source')
    require((b.url, b.db) == ('https://py-staging.odoo.com', 'py19-staging-39654560'), 'Wrong target')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = ROOT / 'outputs/pysb-so-confirm-20261012-staging'
    path = folder / f'{args.mode}-{stamp}.json'
    report = {'mode': args.mode, 'target_database': b.db, 'writes_attempted': False, 'batches': [],
              'confirm_one_by_one': args.confirm_one_by_one,
              'authorization': 'Bruce requested SO confirmation; backup acknowledgement already recorded in this session.'}
    try:
        report.update(preflight(a, b))
        save(path, report)
        eligible = [g for g in report['groups'] if not g['issues']]
        report['exceptions'] = [{'reference': g['source']['name'], 'issues': g['issues']} for g in report['groups'] if g['issues']]
        if args.mode == 'preflight':
            report['status'] = 'read_only'
        else:
            if args.mode == 'sample':
                selected = [min((g for g in eligible if g['before']['state'] in ['draft', 'sent']), key=lambda g: g['source']['id'])]
            else:
                require(args.baseline is not None, 'Passed sample evidence required')
                previous = json.loads(args.baseline.read_text(encoding='utf-8'))
                require(previous['mode'] == 'sample' and previous.get('status') == 'passed' and previous['target_database'] == b.db, 'Invalid sample evidence')
                require([g['source'] for g in previous['groups']] == [g['source'] for g in report['groups']], 'Source changed since sample')
                require(previous['source_lines'] == report['source_lines'], 'Source lines changed since sample')
                selected = eligible
            for start in range(0, len(selected), args.batch_size):
                group = selected[start:start + args.batch_size]
                ids = [g['before']['id'] for g in group]
                require(b.read('sale.order', ids, ORDER) == [g['before'] for g in group], 'SO changed since preflight')
                before_lines = [r for g in group for r in g['lines']]
                require(b.read('sale.order.line', [r['id'] for r in before_lines], LINE) == before_lines, 'Lines changed since preflight')
                entry = {'ids': ids, 'references': [g['source']['name'] for g in group], 'phase': 'confirm_requested'}
                report['batches'].append(entry)
                report['writes_attempted'] = True
                save(path, report)
                pending = [g['before']['id'] for g in group if g['before']['state'] in ['draft', 'sent']]
                if pending:
                    calls = [[i] for i in pending] if args.confirm_one_by_one else [pending]
                    entry['confirm_calls'] = []
                    for call_ids in calls:
                        entry['confirm_calls'].append({'ids': call_ids, 'phase': 'requested'})
                        save(path, report)
                        b.call('sale.order', 'action_confirm', [call_ids], {'context': {'tracking_disable': True, 'mail_auto_subscribe_no_notify': True, 'send_email': False}})
                        entry['confirm_calls'][-1]['phase'] = 'returned'
                        save(path, report)
                entry['phase'] = 'confirmed_pending_date_restore'
                save(path, report)
                dates = defaultdict(list)
                for g in group:
                    dates[g['source']['date_order']].append(g['before']['id'])
                for date, date_ids in dates.items():
                    b.call('sale.order', 'write', [date_ids, {'date_order': date}], {'context': {'tracking_disable': True}})
                entry['after'] = verify_group(b, group)
                entry['phase'] = 'passed'
                save(path, report)
                print(json.dumps({'passed_in_run': start + len(group), 'selected': len(selected), 'last': group[-1]['source']['name']}), flush=True)
            verify_masters(b, report['master_before'])
            report['final_orders'] = b.read('sale.order', [g['before']['id'] for g in report['groups']], ORDER)
            report['final_states'] = dict(Counter(r['state'] for r in report['final_orders']))
            for start in range(0, len(selected), 100):
                verify_group(b, selected[start:start + 100])
            picking_ids = sorted({i for r in report['final_orders'] for i in r['picking_ids']})
            report['pickings'] = b.read('stock.picking', picking_ids, ['name', 'state', 'origin', 'sale_id', 'scheduled_date'])
            report['status'] = 'passed'
    except Exception as exc:
        report['status'] = 'stopped'
        report['error'] = str(exc)
        if report['batches']:
            try:
                report['recovery_read'] = b.read('sale.order', report['batches'][-1]['ids'], ORDER)
            except Exception as read_error:
                report['recovery_read_error'] = str(read_error)
    finally:
        save(path, report)
    print(json.dumps({'report': str(path), 'status': report['status'], 'error': report.get('error'),
                      'initial_states': report.get('initial_states'), 'final_states': report.get('final_states'),
                      'exceptions': report.get('exceptions'), 'writes_attempted': report['writes_attempted']}))
    return 0 if report['status'] != 'stopped' else 1


if __name__ == '__main__':
    raise SystemExit(main())
